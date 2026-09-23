"""Company-wide purchase planning. The user still saves each document."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.exceptions import BusinessRuleError
from core.permissions import HasCompany, get_company_user
from core.services.feature_flags import flag_enabled


def purchase_plan(company, *, warehouse_id=None, supplier_id=None, max_days_to_stockout=None):
    if not flag_enabled(company, "ENABLE_PURCHASE_PLANNING"):
        return None
    if not flag_enabled(company, "ENABLE_REPLENISHMENT"):
        raise BusinessRuleError(
            "Purchase planning needs replenishment turned on for this company.",
            code="replenishment_required",
        )
    from inventory.services import suggest_replenishment
    from inventory.views import low_stock_alert_payload
    from purchases.models import PurchaseInvoice

    as_of = timezone.localdate()
    since = as_of - timedelta(days=14)
    rows = []
    for bal in low_stock_alert_payload(company):
        if not getattr(bal, "is_warehouse_specific", True):
            continue
        if warehouse_id and bal.warehouse_id != int(warehouse_id):
            continue
        suggestion = suggest_replenishment(
            company,
            bal.warehouse,
            bal.product,
            on_hand=bal.on_hand,
            reserved=bal.reserved,
            reorder_level=getattr(bal, "_reorder", None),
            since=since,
            warehouse_specific=True,
        )
        if suggestion.suggested_qty <= 0:
            continue
        daily = suggestion.velocity_14d / Decimal(14) if suggestion.velocity_14d else Decimal("0")
        days = None
        if daily > 0:
            days = int((suggestion.available / daily).to_integral_value())
        if max_days_to_stockout is not None and (days is None or days > int(max_days_to_stockout)):
            continue
        last_supplier = (
            PurchaseInvoice.objects.filter(
                company=company,
                supplier__isnull=False,
                status=PurchaseInvoice.Status.COMPLETED,
                items__product_id=bal.product_id,
            )
            .order_by("-invoice_date", "-id")
            .values_list("supplier_id", flat=True)
            .first()
        )
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
