"""One definition of "low stock" for the whole product (inventory review #20, INV-WP-08).

Everything that shows or counts low stock reads from here: the Low stock page and alerts API, the
Products stock filter, the dashboard tile, the attention/insight alert, Purchase planning and the
``?low_stock=1`` balance filter. Change the rule here and they all move together.

The rule
--------
* Only active items that track stock count. Services and inactive items never alert.
* An item is **low** when it has a reorder rule (a reorder level above zero) and what is available
  is at or below it. Available is on hand less reserved.
* The rule is checked on the company total, unless a godown has its own reorder rule for the item:
  then that godown is checked on its own, against its own level.
* An item with **no** reorder rule and nothing available is **out of stock**, reported apart from
  low stock so the low-stock count is not padded with items nobody reorders.
* An item with a reorder rule that has never had a stock row is low at zero, in the default godown.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, F, Sum

from masters.models import Product

from .models import StockBalance, WarehouseReorderLevel

ZERO = Decimal("0")

LOW = "low"
OUT = "out"
ALL = "all"


def _flag(row, *, scope_godown: bool, available: Decimal, level: Decimal, has_rule: bool):
    row._reorder = level
    row._available = available
    row.is_warehouse_specific = scope_godown
    row.has_reorder_rule = has_rule
    row.stock_status = "OUT" if available <= ZERO else "LOW"
    return row


def low_stock_rows(company, *, status: str = LOW) -> list:
    """Balance-like rows for the items that are low (``status='low'``), out of stock with no reorder
    rule (``'out'``), or both (``'all'``).

    Each row carries ``_reorder``, ``_available``, ``is_warehouse_specific`` (True: this godown's own
    rule; False: company total), ``has_reorder_rule`` and ``stock_status`` ('LOW' or 'OUT').
    """
    override_rows = list(
        WarehouseReorderLevel.objects.filter(company=company).values_list(
            "product_id", "warehouse_id", "reorder_level"
        )
    )
    override_keys = {(pid, wid) for pid, wid, _level in override_rows}
    override_level = {(pid, wid): (level or ZERO) for pid, wid, level in override_rows}

    base = StockBalance.objects.filter(
        company=company, product__status="ACTIVE", product__track_inventory=True
    )
    # One query for every stock-tracked item: its total available, its reorder level, and how many
    # stock rows it has (none at all means it was never stocked).
    product_rows = list(
        Product.objects.filter(company=company, status="ACTIVE", track_inventory=True)
        .order_by()
        .values("id", "reorder_level")
        .annotate(
            available=Sum(F("stock_balances__on_hand") - F("stock_balances__reserved")),
            stock_rows=Count("stock_balances"),
        )
    )
    totals = {row["id"]: row["available"] or ZERO for row in product_rows if row["stock_rows"]}
    reorders = {row["id"]: row["reorder_level"] or ZERO for row in product_rows}
    never_stocked_ids = [
        row["id"] for row in product_rows if not row["stock_rows"] and (row["reorder_level"] or ZERO) > ZERO
    ]

    items: list = []

    # Godown rules: this godown against its own level. A level of zero means no rule here.
    godown_keys = {key for key in override_keys if override_level[key] > ZERO}
    if godown_keys:
        specific = (
            base.filter(
                product_id__in={pid for pid, _wid in godown_keys},
                warehouse_id__in={wid for _pid, wid in godown_keys},
            )
            .select_related("product", "warehouse")
            .annotate(_avail=F("on_hand") - F("reserved"))
        )
        for row in specific:
            key = (row.product_id, row.warehouse_id)
            if key not in godown_keys:
                continue
            level = override_level[key]
            if row._avail <= level:
                items.append(_flag(row, scope_godown=True, available=row._avail, level=level, has_rule=True))

    # Company totals: the item against its own reorder level (or "out" when it has none).
    wanted: dict[int, bool] = {}
    for pid, available in totals.items():
        level = reorders.get(pid, ZERO)
        if level > ZERO and available <= level:
            wanted[pid] = True
        elif level <= ZERO and available <= ZERO:
            wanted[pid] = False
    if wanted:
        seen: set[int] = set()
        candidates = (
            base.filter(product_id__in=wanted)
            .select_related("product", "warehouse")
            .order_by("product_id", "id")
        )
        for row in candidates:
            if row.product_id in seen:
                continue
            # A godown that has its own rule is judged above, not as part of the total.
            if (row.product_id, row.warehouse_id) in override_keys:
                continue
            seen.add(row.product_id)
            available = totals[row.product_id]
            row.on_hand = available
            row.reserved = ZERO
            items.append(
                _flag(
                    row,
                    scope_godown=False,
                    available=available,
                    level=reorders[row.product_id],
                    has_rule=wanted[row.product_id],
                )
            )

    # Items with a reorder rule that never had a stock row: low at zero in the default godown.
    if never_stocked_ids:
        from .services import InventoryService

        warehouse = InventoryService.default_warehouse(company)
        for product in Product.objects.filter(company=company, pk__in=never_stocked_ids):
            row = StockBalance(
                company=company, product=product, warehouse=warehouse, on_hand=ZERO, reserved=ZERO,
            )
            items.append(
                _flag(row, scope_godown=False, available=ZERO, level=product.reorder_level or ZERO, has_rule=True)
            )

    if status == LOW:
        return [row for row in items if row.has_reorder_rule]
    if status == OUT:
        return [row for row in items if not row.has_reorder_rule]
    return items


def low_stock_product_ids(company) -> set[int]:
    """Products that are low anywhere (company total or a godown's own rule)."""
    return {row.product_id for row in low_stock_rows(company, status=LOW)}
