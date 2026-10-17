"""Company-wide purchase planning. The user still saves each document."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.permissions import SubscriptionWritesAllowed
from core.exceptions import BusinessRuleError
from core.idempotency import wrap_idempotent
from core.permissions import (
    CanCreatePurchases,
    CanViewInventorySurfaces,
    HasCompany,
    can_see_product_cost,
    get_company_user,
)
from core.services.feature_flags import flag_enabled


# Units a buyer can order in parts. Everything else (pieces, boxes, bags...) is ordered whole.
FRACTIONAL_UQC = {
    "KGS", "GMS", "QTL", "TON", "MTS", "KLR", "LTR", "MLT", "MTR", "CMS", "SQM", "SQF", "SQY", "CBM",
    "CCM", "TNE", "BDL",
}


def _whole_units_only(product) -> bool:
    unit = getattr(product, "unit", None)
    return (getattr(unit, "uqc_code", "") or "").strip().upper() not in FRACTIONAL_UQC


def purchase_plan(company, *, warehouse_id=None, supplier_id=None, max_days_to_stockout=None):
    """What to buy or move, from the same low-stock rows every other screen uses (INV-WP-09).

    * Godown rows (an item's own reorder rule at one godown) go to that godown.
    * Company-wide rows (the item is low across all godowns) go to the default godown.
    * What is already on open (draft) purchase orders is taken off the suggestion, so asking twice
      does not order twice.
    """
    if not flag_enabled(company, "ENABLE_PURCHASE_PLANNING"):
        return None
    if not flag_enabled(company, "ENABLE_REPLENISHMENT"):
        raise BusinessRuleError(
            "Purchase planning needs replenishment turned on for this company.",
            code="replenishment_required",
        )
    from inventory.forecast import godown_velocity, item_velocity
    from inventory.low_stock import low_stock_rows
    from inventory.reorder_maps import (
        last_completed_suppliers,
        last_purchase_prices,
        open_order_quantities,
        reorder_and_balances,
    )
    from inventory.services import InventoryService, suggest_replenishment
    from masters.models import Supplier

    default_wh = InventoryService.default_warehouse(company)

    def destination(bal):
        return bal.warehouse if getattr(bal, "is_warehouse_specific", False) else default_wh

    balances = low_stock_rows(company, status="low")
    if warehouse_id:
        balances = [bal for bal in balances if destination(bal).id == int(warehouse_id)]
    product_ids = {bal.product_id for bal in balances}
    reorder_row_by_key, levels_by_product, balances_by_product = reorder_and_balances(company, product_ids)
    suppliers = last_completed_suppliers(company, product_ids)
    supplier_names = dict(
        Supplier.objects.filter(pk__in=set(suppliers.values())).values_list("id", "name")
    )

    # Quantity already promised to suppliers (recent drafts and orders not yet received), shared with
    # the demand forecast. Old forgotten drafts are listed, not counted (INV-IDR-08).
    counted_on_order, stale_on_order = open_order_quantities(company, product_ids)
    remaining_on_order = {pid: Decimal(str(qty)) for pid, qty in counted_on_order.items()}
    on_order_total = dict(remaining_on_order)
    # One definition of sales pace, shared with the demand forecast (INV-WP-10): company-wide for an
    # item that is low everywhere, and the same measure at the godown for a godown's own rule.
    company_velocity = item_velocity(company, product_ids)
    specific_godowns = {bal.warehouse_id for bal in balances if getattr(bal, "is_warehouse_specific", False)}
    godown_pace = godown_velocity(company, specific_godowns, product_ids) if specific_godowns else {}
    last_prices = last_purchase_prices(company, product_ids)

    rows = []
    covered = 0
    for bal in balances:
        specific = bool(getattr(bal, "is_warehouse_specific", False))
        if specific:
            suggestion = suggest_replenishment(
                company,
                bal.warehouse,
                bal.product,
                on_hand=bal.on_hand,
                reserved=bal.reserved,
                reorder_level=getattr(bal, "_reorder", None),
                since=None,
                warehouse_specific=True,
                reorder_level_row=reorder_row_by_key.get((bal.warehouse_id, bal.product_id)),
                warehouse_levels=levels_by_product.get(bal.product_id, {}),
                product_balances=balances_by_product.get(bal.product_id, []),
                velocity_per_day=godown_pace.get((bal.product_id, bal.warehouse_id), Decimal("0")),
            )
            velocity = suggestion.velocity_per_day
        else:
            # Low across the whole company: no single godown to move stock into, so buy, and judge
            # the pace of sales on the whole company rather than on one godown.
            suggestion = suggest_replenishment(
                company, None, bal.product,
                on_hand=bal.on_hand, reserved=bal.reserved,
                reorder_level=getattr(bal, "_reorder", None), since=None, warehouse_specific=False,
                reorder_level_row=None, warehouse_levels={}, product_balances=[],
                velocity_per_day=company_velocity.get(bal.product_id, Decimal("0")),
            )
            velocity = suggestion.velocity_per_day
        wanted = suggestion.suggested_qty
        if wanted <= 0:
            continue
        daily = velocity if velocity else Decimal("0")
        days = None
        if daily > 0:
            days = int((suggestion.available / daily).to_integral_value())
        if max_days_to_stockout is not None and (days is None or days > int(max_days_to_stockout)):
            continue
        last_supplier = suppliers.get(bal.product_id)
        if supplier_id and last_supplier != int(supplier_id):
            continue
        dest = destination(bal)
        master_price = bal.product.purchase_price or Decimal("0")
        common = {
            "product_id": bal.product_id,
            "product_name": bal.product.name,
            "unit": getattr(getattr(bal.product, "unit", None), "short_name", "") or "",
            "warehouse_id": dest.id,
            "warehouse_name": dest.name,
            "scope": "godown" if specific else "company",
            "available": str(suggestion.available),
            "reorder_level": str(suggestion.reorder_level),
            "days_to_stockout": days,
            "supplier_id": last_supplier,
            "supplier_name": supplier_names.get(last_supplier, "") if last_supplier else "",
            # The price on the latest completed bill; the item master's price when it was never bought.
            "last_price": str(last_prices.get(bal.product_id, master_price)),
            "master_price": str(master_price),
            "whole_units_only": _whole_units_only(bal.product),
        }
        # A donor godown can only give its surplus: move that, and buy the rest.
        transfer_qty = suggestion.transfer_qty if suggestion.transfer_from_warehouse_id else Decimal("0")
        buy_qty = wanted - transfer_qty
        if transfer_qty > 0:
            rows.append({
                **common,
                "on_order": "0",
                "suggested_qty": str(transfer_qty),
                "transfer_from_warehouse_id": suggestion.transfer_from_warehouse_id,
                "transfer_from_warehouse_name": suggestion.transfer_from_warehouse_name,
            })
        if buy_qty > 0:
            # Take what is already on order off what is wanted (a transfer is never covered by a PO).
            ordered = min(buy_qty, remaining_on_order.get(bal.product_id, Decimal("0")))
            remaining_on_order[bal.product_id] = remaining_on_order.get(bal.product_id, Decimal("0")) - ordered
            qty = (buy_qty - ordered).quantize(Decimal("0.001"))
            if qty <= 0:
                covered += 1
                continue
            rows.append({
                **common,
                "on_order": str(on_order_total.get(bal.product_id, Decimal("0"))),
                "suggested_qty": str(qty),
                "transfer_from_warehouse_id": None,
                "transfer_from_warehouse_name": None,
            })
    documents = _documents(rows)
    stale = [
        {"product_id": pid, "quantity": str(qty)} for pid, qty in sorted(stale_on_order.items())
        if pid in product_ids
    ]
    return {"rows": rows, "documents": documents, "covered_by_orders": covered, "stale_drafts": stale}


def _documents(rows: list[dict]) -> list[dict]:
    purchases = defaultdict(list)
    transfers = defaultdict(list)
    for row in rows:
        line = {
            "product_id": row["product_id"],
            "qty": row["suggested_qty"],
            "warehouse_id": row["warehouse_id"],
        }
        if row["transfer_from_warehouse_id"]:
            transfers[(row["transfer_from_warehouse_id"], row["warehouse_id"])].append(line)
        else:
            purchases[row["supplier_id"]].append(line)
    documents = []
    for supplier_id, lines in sorted(purchases.items(), key=lambda item: (item[0] is None, item[0] or 0)):
        documents.append({"kind": "purchase", "supplier_id": supplier_id, "lines": lines})
    for (source_id, dest_id), lines in sorted(transfers.items(), key=lambda item: (item[0][0] or 0, item[0][1] or 0)):
        documents.append({
            "kind": "transfer",
            "from_warehouse_id": source_id,
            "to_warehouse_id": dest_id,
            "lines": lines,
        })
    return documents


class PurchasePlanningView(APIView):
    permission_classes = [IsAuthenticated, HasCompany]

    def get_permissions(self):
        # POST creates real PurchaseOrder records, so it needs the same
        # write-gates every other PO-creation endpoint enforces
        # (purchases/views.py, purchases/phase1_views.py).
        if self.request.method == "POST":
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCreatePurchases()]
        # INV-WP-04: the page is gated by canViewInventorySurfaces; the API must be too, or a
        # VIEWER can read suggested quantities and last suppliers by calling it directly.
        return [IsAuthenticated(), HasCompany(), CanViewInventorySurfaces()]

    def get(self, request):
        company = get_company_user(request).company
        if not flag_enabled(company, "ENABLE_PURCHASE_PLANNING"):
            return Response({"detail": "Not found."}, status=404)
        try:
            plan = purchase_plan(
                company,
                warehouse_id=request.query_params.get("warehouse"),
                supplier_id=request.query_params.get("supplier"),
                max_days_to_stockout=request.query_params.get("urgency"),
            )
        except BusinessRuleError as exc:
            return Response({"detail": str(exc), "code": "replenishment_required"}, status=400)
        if plan and not can_see_product_cost(request):
            # INV-IDR-12: what an item costs is for people who buy, stock or read the books.
            for row in plan["rows"]:
                row.pop("last_price", None)
                row.pop("master_price", None)
        return Response(plan)

    def post(self, request):
        """Create one draft purchase order per supplier. Sending stays a separate action."""
        cu = get_company_user(request)
        company = cu.company
        if not flag_enabled(company, "ENABLE_PURCHASE_PLANNING"):
            return Response({"detail": "Not found."}, status=404)
        body_rows = request.data.get("rows") if isinstance(request.data, dict) else None
        if isinstance(body_rows, list) and body_rows:
            rows = body_rows
        else:
            try:
                plan = purchase_plan(company)
            except BusinessRuleError as exc:
                return Response({"detail": str(exc)}, status=400)
            if not plan:
                return Response({"detail": "Not found."}, status=404)
            rows = plan["rows"]
        confirm_duplicate = bool(request.data.get("confirm_duplicate")) if isinstance(request.data, dict) else False

        def build():
            try:
                created, needs_supplier, needs_transfer = materialize_supplier_drafts(
                    company, cu.user, rows, confirm_duplicate=confirm_duplicate,
                )
            except BusinessRuleError as exc:
                return Response(
                    {"detail": str(exc), "code": str(exc.get_codes())}, status=400,
                )
            return Response({
                "purchase_order_ids": [order.id for order in created],
                "needs_supplier": needs_supplier,
                "needs_transfer": needs_transfer,
            })

        # INV-IDR-08: a double click or a retry after a lost answer is one set of drafts, not two.
        return wrap_idempotent(request=request, company=company, scope="purchase_planning_drafts", build=build)


DUPLICATE_DRAFT_MINUTES = 60


@transaction.atomic
def materialize_supplier_drafts(company, user, rows, *, confirm_duplicate: bool = False):
    """One draft PO per supplier. Rows without a supplier, or that resolve to an
    inter-warehouse transfer instead of a purchase, are returned aside so the
    caller can still see and action them.

    A product that already sits on a draft order for the same supplier created in the last hour is
    refused (``duplicate_draft``) unless ``confirm_duplicate`` is set, so pressing the button twice
    from two tabs does not order everything twice."""
    from decimal import ROUND_CEILING, Decimal, InvalidOperation

    from masters.models import Product, Supplier
    from purchases.models import PurchaseOrder
    from purchases.notes_services import PurchaseNotesService

    grouped: dict = {}
    needs_supplier = []
    needs_transfer = []
    for row in rows:
        if row.get("transfer_from_warehouse_id"):
            needs_transfer.append(row)
            continue
        if not row.get("supplier_id"):
            needs_supplier.append(row)
            continue
        try:
            supplier_id = int(row["supplier_id"])
        except (KeyError, TypeError, ValueError):
            raise BusinessRuleError("Each row needs a valid supplier_id.")
        grouped.setdefault(supplier_id, []).append(row)
    created = []
    for supplier_id, lines in grouped.items():
        try:
            supplier = Supplier.objects.get(pk=supplier_id, company=company)
        except Supplier.DoesNotExist:
            raise BusinessRuleError(f"Supplier {supplier_id} was not found.")
        notes = []
        items = []
        recent = _recent_draft_products(company, supplier_id, [line.get("product_id") for line in lines])
        for line in lines:
            product_id = line.get("product_id")
            if not product_id:
                raise BusinessRuleError("Each row needs a product_id.")
            if not confirm_duplicate and int(product_id) in recent:
                raise BusinessRuleError(
                    "A draft order for this supplier with this item was created in the last hour. "
                    "Open it, or confirm to create another.",
                    code="duplicate_draft",
                )
            try:
                product = Product.objects.get(pk=product_id, company=company)
            except Product.DoesNotExist:
                raise BusinessRuleError(f"Product {product_id} was not found.")
            try:
                qty = Decimal(str(line["suggested_qty"]))
            except (KeyError, InvalidOperation, TypeError):
                raise BusinessRuleError(f"{product.name} needs a valid suggested_qty.")
            if qty <= 0:
                raise BusinessRuleError(f"{product.name} needs a quantity above zero.")
            # Pieces and boxes are ordered whole; weights and lengths keep their decimals.
            rounded = qty.to_integral_value(rounding=ROUND_CEILING) if _whole_units_only(product) else qty
            if rounded != qty:
                notes.append(f"{product.name} rounded from {qty} to {rounded}")
            if line.get("warehouse_name"):
                notes.append(f"{product.name} for {line['warehouse_name']}")
            items.append({
                "product": product,
                "quantity": rounded,
                "unit_price": product.purchase_price or Decimal("0"),
                "gst_rate": product.gst_rate,
            })
        order = PurchaseOrder.objects.create(
            company=company,
            supplier=supplier,
            notes="; ".join(notes),
            created_by=user,
            updated_by=user,
        )
        PurchaseNotesService.set_order_items(order, items, user)
        created.append(order)
    return created, needs_supplier, needs_transfer


def _recent_draft_products(company, supplier_id, product_ids) -> set[int]:
    from datetime import timedelta

    from purchases.models import PurchaseOrder, PurchaseOrderItem

    wanted = [int(p) for p in product_ids if str(p).isdigit()]
    if not wanted:
        return set()
    since = timezone.now() - timedelta(minutes=DUPLICATE_DRAFT_MINUTES)
    return set(
        PurchaseOrderItem.objects.filter(
            company=company, product_id__in=wanted, purchase_order__supplier_id=supplier_id,
            purchase_order__status=PurchaseOrder.Status.DRAFT, purchase_order__created_at__gte=since,
        ).values_list("product_id", flat=True)
    )
