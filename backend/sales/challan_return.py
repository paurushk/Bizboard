"""Delivery challan return — partial quantities, stock in on complete if DC posted stock."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.services.tax_engine.registry import get_tax_engine
from core.services.document_numbers import DocumentNumberService, resolve_series_gstin

from .models import (
    DeliveryChallan,
    DeliveryChallanItem,
    DeliveryChallanReturn,
    DeliveryChallanReturnItem,
)
from .services import _build_items, _validate_lines


class ChallanReturnService:
    @staticmethod
    def returned_quantities(challan, exclude_return=None):
        qs = DeliveryChallanReturnItem.objects.filter(
            challan_return__challan=challan,
            challan_return__status=DeliveryChallanReturn.Status.COMPLETED,
        )
        if exclude_return is not None:
            qs = qs.exclude(challan_return=exclude_return)
        return {
            row["product"]: row["total"]
            for row in qs.values("product").annotate(total=Sum("quantity"))
        }

    @staticmethod
    @transaction.atomic
    def set_items(challan_return: DeliveryChallanReturn, items_data, user):
        if challan_return.status != DeliveryChallanReturn.Status.DRAFT:
            raise BusinessRuleError("Completed challan return cannot be edited.")
        _validate_lines(items_data, challan_return.company, check_active=False)
        already = ChallanReturnService.returned_quantities(
            challan_return.challan, exclude_return=challan_return
        )
        remaining = {
            item.product_id: item.quantity - already.get(item.product_id, Decimal("0"))
            for item in challan_return.challan.items.all()
        }
        for line in items_data:
            pid = line["product"].pk
            qty = Decimal(str(line["quantity"]))
            left = remaining.get(pid, Decimal("0"))
            if qty > left:
                raise BusinessRuleError(
                    f"Return quantity {qty} exceeds remaining challan quantity {left} for this product."
                )
        challan_return.items.all().delete()
        items = _build_items(DeliveryChallanReturnItem, "challan_return", challan_return, items_data)
        get_tax_engine(challan_return.company).compute_document_totals(
            challan_return, items, tax_enabled=False, intra_state=True,
        )
        DeliveryChallanReturnItem.objects.bulk_create(items)
        challan_return.updated_by = user
        challan_return.save()
        return challan_return

    @staticmethod
    @transaction.atomic
    def complete(challan_return: DeliveryChallanReturn, user):
        challan_return = DeliveryChallanReturn.objects.select_for_update().get(pk=challan_return.pk)
        if challan_return.status != DeliveryChallanReturn.Status.DRAFT:
            raise BusinessRuleError(f"Cannot complete a return in status {challan_return.status}.")
        if not challan_return.items.exists():
            raise BusinessRuleError("Add at least one line before completing the challan return.")
        ChallanReturnService.set_items(
            challan_return,
            [
                {
                    "product": i.product,
                    "quantity": i.quantity,
                    "unit_price": i.unit_price,
                    "description": i.description,
                    "gst_rate": i.gst_rate,
                }
                for i in challan_return.items.select_related("product")
            ],
            user,
        )
        challan = DeliveryChallan.objects.select_for_update().get(pk=challan_return.challan_id)
        if challan.status != DeliveryChallan.Status.COMPLETED:
            raise BusinessRuleError("Only a completed delivery challan can be returned.")
        if challan.converted_invoice_id:
            # Converting to an invoice leaves the challan COMPLETED (status is
            # not transitioned) — without this check both this path and the
            # invoice's own Sales Return could reverse the same physical
            # stock. Once invoiced, returns must go through the Sales Return
            # flow against that invoice instead.
            raise BusinessRuleError(
                "This delivery challan has already been converted to an invoice — "
                "use a Sales Return against that invoice instead."
            )
        if not challan_return.number:
            challan_return.number = DocumentNumberService.next_number(
                challan_return.company,
                "DELIVERY_CHALLAN_RETURN",
                gstin=resolve_series_gstin(challan_return.company),
                on_date=challan_return.return_date,
            )
        if challan.stock_posted:
            from .cogs_service import CogsService

            CogsService.restore_challan_return_stock_and_cogs(
                challan_return,
                challan,
                list(challan_return.items.select_related("product")),
                user,
            )
        challan_return.status = DeliveryChallanReturn.Status.COMPLETED
        challan_return.completed_at = timezone.now()
        challan_return.updated_by = user
        challan_return.save()
        return challan_return
