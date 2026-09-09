"""Inventory invariants — stock ledger, godowns, batches/expiry, serial
traceability, and running cost.

Core rule: ``StockMovement`` is an append-only signed ledger; every derived
cache (``StockBalance``, ``InventoryRunningCost``, ``InventoryCostLayer``) must
reconcile to it exactly. Imports are lazy to avoid an app import cycle.
"""

from __future__ import annotations

from decimal import Decimal

from .base import invariant

_ZERO = Decimal("0")

# Movement types whose sign is negative (stock leaving a location) — an "issue".
_ISSUE_TYPES = ("SALE", "PURCHASE_RETURN", "TRANSFER_OUT", "MANUFACTURE_ISSUE")


def _key_qty_from_movements(company):
    """{(warehouse_id, product_id, batch_id): signed qty} from the movement ledger."""
    from django.db.models import Sum

    from inventory.models import StockMovement

    out: dict[tuple, Decimal] = {}
    for r in (
        StockMovement.objects.filter(company=company)
        .values("warehouse_id", "product_id", "batch_id")
        .annotate(q=Sum("quantity"))
    ):
        out[(r["warehouse_id"], r["product_id"], r["batch_id"])] = r["q"] or _ZERO
    return out


@invariant(
    "inventory.balance_equals_movements",
    consequence="StockBalance.on_hand has drifted from the sum of stock movements — every quantity/valuation/COGS read off it is wrong.",
)
def balance_equals_movements(company) -> list[str]:
    from inventory.models import StockBalance

    moves = _key_qty_from_movements(company)
    seen = set()
    out = []
    for b in StockBalance.objects.filter(company=company).values(
        "warehouse_id", "product_id", "batch_id", "on_hand"
    ):
        key = (b["warehouse_id"], b["product_id"], b["batch_id"])
        seen.add(key)
        expected = moves.get(key, _ZERO)
        if (b["on_hand"] or _ZERO) != expected:
            out.append(
                f"balance {key}: on_hand {b['on_hand']} != Σmovements {expected}"
            )
    for key, qty in moves.items():
        if key not in seen and qty != _ZERO:
            out.append(f"movements net to {qty} for {key} but no StockBalance row exists")
    return out


@invariant(
    "inventory.running_cost_qty_matches_movements",
    consequence="InventoryRunningCost.qty disagrees with the movement ledger — perpetual valuation is corrupt.",
)
def running_cost_qty_matches_movements(company) -> list[str]:
    from inventory.models import InventoryRunningCost

    moves = _key_qty_from_movements(company)
    out = []
    for rc in InventoryRunningCost.objects.filter(company=company).values(
        "warehouse_id", "product_id", "batch_id", "qty"
    ):
        key = (rc["warehouse_id"], rc["product_id"], rc["batch_id"])
        expected = moves.get(key, _ZERO)
        if (rc["qty"] or _ZERO) != expected:
            out.append(f"running cost {key}: qty {rc['qty']} != Σmovements {expected}")
    return out


# NOT registered: perpetual FIFO cost layers are explicitly NOT the pilot cost
# model (FREEZE_SCOPE C3 — running weighted cost is). Layers are best-effort and
# not maintained on every path (e.g. add_stock openings). A dedicated FIFO chain
# calls this directly if/when FIFO COGS enters scope.
def cost_layers_reconcile(company) -> list[str]:
    from django.db.models import Sum

    from inventory.models import InventoryCostLayer, StockBalance

    # Perpetual FIFO layers are NOT the pilot cost model (FREEZE_SCOPE C3 — running
    # weighted cost is). Only assert reconciliation for (wh, product, batch) keys
    # that actually have layers; a key with none is the normal running-cost path.
    layer_qty: dict[tuple, Decimal] = {}
    for r in (
        InventoryCostLayer.objects.filter(company=company)
        .values("warehouse_id", "product_id", "batch_id")
        .annotate(q=Sum("qty_remaining"))
    ):
        layer_qty[(r["warehouse_id"], r["product_id"], r["batch_id"])] = r["q"] or _ZERO
    if not layer_qty:
        return []
    balances = {
        (b["warehouse_id"], b["product_id"], b["batch_id"]): (b["on_hand"] or _ZERO)
        for b in StockBalance.objects.filter(company=company).values(
            "warehouse_id", "product_id", "batch_id", "on_hand"
        )
    }
    out = []
    for key, got in layer_qty.items():
        on_hand = balances.get(key, _ZERO)
        if got != max(on_hand, _ZERO):
            out.append(
                f"cost layers {key}: Σqty_remaining {got} != on_hand {on_hand}"
            )
    return out


@invariant(
    "inventory.no_negative_balance_when_blocked",
    consequence="Stock went negative under a BLOCK negative-stock policy, or a reserved quantity is negative.",
)
def no_negative_balance_when_blocked(company) -> list[str]:
    from inventory.models import StockBalance

    out = []
    if str(getattr(company, "negative_stock_policy", "BLOCK")).upper() == "BLOCK":
        neg = StockBalance.objects.filter(company=company, on_hand__lt=0).values_list(
            "warehouse_id", "product_id", "batch_id", "on_hand"
        )
        for wh, pr, ba, oh in neg:
            out.append(f"negative on_hand {oh} at (wh={wh}, product={pr}, batch={ba}) under BLOCK policy")
    for wh, pr, ba, rs in StockBalance.objects.filter(company=company, reserved__lt=0).values_list(
        "warehouse_id", "product_id", "batch_id", "reserved"
    ):
        out.append(f"negative reserved {rs} at (wh={wh}, product={pr}, batch={ba})")
    return out


@invariant(
    "inventory.batch_tenancy_consistent",
    consequence="A movement/balance/cost row points at a BatchLot from a different company or product.",
)
def batch_tenancy_consistent(company) -> list[str]:
    from django.db.models import F, Q

    from inventory.models import InventoryRunningCost, StockBalance, StockMovement

    out = []
    for model, label in (
        (StockMovement, "movement"),
        (StockBalance, "balance"),
        (InventoryRunningCost, "running_cost"),
    ):
        bad = (
            model.objects.filter(company=company, batch__isnull=False)
            .filter(~Q(batch__company_id=company.id) | ~Q(batch__product_id=F("product_id")))
            .count()
        )
        if bad:
            out.append(f"{bad} {label} row(s) referencing a foreign/mismatched BatchLot")
    return out


@invariant(
    "inventory.no_expired_issue_when_blocked",
    consequence="Stock was issued from a batch after its expiry date while block_expired_stock is on.",
)
def no_expired_issue_when_blocked(company) -> list[str]:
    from django.db.models import F

    from inventory.models import StockMovement

    if not getattr(company, "block_expired_stock", False):
        return []
    bad = StockMovement.objects.filter(
        company=company,
        movement_type__in=_ISSUE_TYPES,
        batch__isnull=False,
        batch__expiry_date__isnull=False,
        movement_date__gt=F("batch__expiry_date"),
    ).values_list("id", "movement_type", "movement_date", "batch__batch_no")[:20]
    return [
        f"movement #{mid} {mt} on {md} issued expired batch {bn}"
        for mid, mt, md, bn in bad
    ]


@invariant(
    "inventory.transfer_pairs_net_zero",
    consequence="Inter-godown transfers don't net to zero per product — stock was created or destroyed in transit.",
)
def transfer_pairs_net_zero(company) -> list[str]:
    from django.db.models import Sum

    from inventory.models import StockMovement

    rows = (
        StockMovement.objects.filter(
            company=company, movement_type__in=["TRANSFER_OUT", "TRANSFER_IN"]
        )
        .values("product_id", "batch_id")
        .annotate(net=Sum("quantity"))
    )
    return [
        f"transfers for (product={r['product_id']}, batch={r['batch_id']}) net to {r['net']}, not 0"
        for r in rows
        if (r["net"] or _ZERO) != _ZERO
    ]


@invariant(
    "inventory.serial_traceability",
    consequence="Serial-number records are inconsistent with stock on hand — goods cannot be traced unit to unit.",
)
def serial_traceability(company) -> list[str]:
    from django.db.models import Count, Sum

    from inventory.models import SerialNumber, StockBalance

    out = []
    available_no_wh = SerialNumber.objects.filter(
        company=company, status=SerialNumber.Status.AVAILABLE, warehouse__isnull=True
    ).count()
    if available_no_wh:
        out.append(f"{available_no_wh} AVAILABLE serial(s) with no godown")

    # For each product/warehouse that has serials, AVAILABLE serial count must
    # not exceed physical on-hand for that product in that warehouse.
    per_loc = (
        SerialNumber.objects.filter(company=company, status=SerialNumber.Status.AVAILABLE)
        .values("product_id", "warehouse_id")
        .annotate(n=Count("id"))
    )
    for r in per_loc:
        on_hand = (
            StockBalance.objects.filter(
                company=company, product_id=r["product_id"], warehouse_id=r["warehouse_id"]
            ).aggregate(q=Sum("on_hand"))["q"]
            or _ZERO
        )
        if r["n"] > on_hand:
            out.append(
                f"product {r['product_id']} @ wh {r['warehouse_id']}: "
                f"{r['n']} AVAILABLE serials > {on_hand} on hand"
            )
    return out
