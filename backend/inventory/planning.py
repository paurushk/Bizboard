"""Company-wide purchase planning. The user still saves each document."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.permissions import SubscriptionWritesAllowed
from core.exceptions import BusinessRuleError
from core.permissions import CanCreatePurchases, HasCompany, get_company_user
from core.services.feature_flags import flag_enabled


def purchase_plan(company, *, warehouse_id=None, supplier_id=None, max_days_to_stockout=None):
    if not flag_enabled(company, "ENABLE_PURCHASE_PLANNING"):
        return None
    if not flag_enabled(company, "ENABLE_REPLENISHMENT"):
        raise BusinessRuleError(
            "Purchase planning needs replenishment turned on for this company.",
            code="replenishment_required",
        )
    from inventory.reorder_maps import last_completed_suppliers, reorder_and_balances
    from inventory.services import suggest_replenishment
    from inventory.views import low_stock_alert_payload

    as_of = timezone.localdate()
    since = as_of - timedelta(days=14)
    balances = [
        bal for bal in low_stock_alert_payload(company)
        if getattr(bal, "is_warehouse_specific", True)
        and (not warehouse_id or bal.warehouse_id == int(warehouse_id))
    ]
    product_ids = {bal.product_id for bal in balances}
    reorder_row_by_key, levels_by_product, balances_by_product = reorder_and_balances(company, product_ids)
    suppliers = last_completed_suppliers(company, product_ids)
    rows = []
    for bal in balances:
        suggestion = suggest_replenishment(
            company,
            bal.warehouse,
            bal.product,
            on_hand=bal.on_hand,
            reserved=bal.reserved,
            reorder_level=getattr(bal, "_reorder", None),
            since=since,
            warehouse_specific=True,
            reorder_level_row=reorder_row_by_key.get((bal.warehouse_id, bal.product_id)),
            warehouse_levels=levels_by_product.get(bal.product_id, {}),
            product_balances=balances_by_product.get(bal.product_id, []),
        )
        if suggestion.suggested_qty <= 0:
            continue
        daily = suggestion.velocity_14d / Decimal(14) if suggestion.velocity_14d else Decimal("0")
        days = None
        if daily > 0:
            days = int((suggestion.available / daily).to_integral_value())
        if max_days_to_stockout is not None and (days is None or days > int(max_days_to_stockout)):
            continue
        last_supplier = suppliers.get(bal.product_id)
        if supplier_id and last_supplier != int(supplier_id):
            continue
        rows.append({
            "product_id": bal.product_id,
            "product_name": bal.product.name,
            "warehouse_id": bal.warehouse_id,
            "warehouse_name": bal.warehouse.name if bal.warehouse_id else "",
            "suggested_qty": str(suggestion.suggested_qty),
            "days_to_stockout": days,
            "supplier_id": last_supplier,
            "transfer_from_warehouse_id": suggestion.transfer_from_warehouse_id,
            "transfer_from_warehouse_name": suggestion.transfer_from_warehouse_name,
        })
    documents = _documents(rows)
    return {"rows": rows, "documents": documents}


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
        return super().get_permissions()

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
        try:
            created, needs_supplier, needs_transfer = materialize_supplier_drafts(company, cu.user, rows)
        except BusinessRuleError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({
            "purchase_order_ids": [order.id for order in created],
            "needs_supplier": needs_supplier,
            "needs_transfer": needs_transfer,
        })


@transaction.atomic
def materialize_supplier_drafts(company, user, rows):
    """One draft PO per supplier. Rows without a supplier, or that resolve to an
    inter-warehouse transfer instead of a purchase, are returned aside so the
    caller can still see and action them."""
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
        for line in lines:
            product_id = line.get("product_id")
            if not product_id:
                raise BusinessRuleError("Each row needs a product_id.")
            try:
                product = Product.objects.get(pk=product_id, company=company)
            except Product.DoesNotExist:
                raise BusinessRuleError(f"Product {product_id} was not found.")
            try:
                qty = Decimal(str(line["suggested_qty"]))
            except (KeyError, InvalidOperation, TypeError):
                raise BusinessRuleError(f"{product.name} needs a valid suggested_qty.")
            rounded = qty.to_integral_value(rounding=ROUND_CEILING)
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
