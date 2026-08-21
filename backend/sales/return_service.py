"""Sales return lifecycle — extracted from SalesService (BB-000476)."""

from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.events import emit
from core.exceptions import BusinessRuleError
from core.services.billing import compute_document_totals
from core.services.document_numbers import DocumentNumberService, resolve_series_gstin
from core.services.place_of_supply import party_intra_state
from inventory.models import MovementType, StockMovement
from inventory.services import InventoryService, SerialNumberService

from .models import (
    NoteReason,
    SalesCreditNote,
    SalesInvoice,
    SalesReturn,
    SalesReturnItem,
)
from .services import _build_items, _tax_enabled, _validate_lines


class ReturnService:
    @staticmethod
    @transaction.atomic
    def set_return_items(sales_return: SalesReturn, items_data, user):
        if sales_return.status != SalesReturn.Status.DRAFT:
            raise BusinessRuleError("Completed return cannot be edited.")
        _validate_lines(items_data, sales_return.company, check_active=False)
        sales_return.items.all().delete()
        items = _build_items(SalesReturnItem, "sales_return", sales_return, items_data)
        compute_document_totals(
            sales_return,
            items,
            tax_enabled=_tax_enabled(sales_return.sales_invoice.invoice_type),
            intra_state=party_intra_state(
                sales_return.company,
                sales_return.customer.state,
                sales_return.customer.gstin or "",
            ),
        )
        SalesReturnItem.objects.bulk_create(items)
        sales_return.updated_by = user
        sales_return.save()
        return sales_return

    @staticmethod
    def returned_quantities(invoice, exclude_return=None):
        qs = SalesReturnItem.objects.filter(
            sales_return__sales_invoice=invoice,
            sales_return__status=SalesReturn.Status.COMPLETED,
        )
        if exclude_return is not None:
            qs = qs.exclude(sales_return=exclude_return)
        return {
            row["product"]: row["total"]
            for row in qs.values("product").annotate(total=Sum("quantity"))
        }

    @staticmethod
    @transaction.atomic
    def complete_return(sales_return: SalesReturn, user):
        from .cogs_service import CogsService

        sales_return = SalesReturn.objects.select_for_update().get(pk=sales_return.pk)
        from reporting.gst_periods import assert_period_allows_money_amend

        assert_period_allows_money_amend(sales_return.company, sales_return.return_date)
        if sales_return.status != SalesReturn.Status.DRAFT:
            raise BusinessRuleError(f"Cannot complete a return in status {sales_return.status}.")
        invoice = sales_return.sales_invoice
        if invoice.status not in (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED):
            raise BusinessRuleError("Sales return must reference a completed invoice.")
        if (
            sales_return.return_date
            and invoice.invoice_date
            and sales_return.return_date < invoice.invoice_date
        ):
            raise BusinessRuleError(
                "Return date cannot be before the original invoice date."
            )
        items = list(sales_return.items.select_related("product"))
        if not items:
            raise BusinessRuleError("Cannot complete a return without line items.")

        sold = {
            row["product"]: row["total"]
            for row in invoice.items.values("product").annotate(total=Sum("quantity"))
        }
        already = ReturnService.returned_quantities(invoice)
        requested = defaultdict(Decimal)
        for item in items:
            requested[item.product_id] += item.quantity
        for product_id, qty in requested.items():
            remaining = sold.get(product_id, Decimal("0")) - already.get(product_id, Decimal("0"))
            if qty > remaining:
                raise BusinessRuleError(
                    f"Return quantity {qty} exceeds remaining returnable quantity {remaining}."
                )

        sales_return.number = DocumentNumberService.next_number(
            sales_return.company,
            "SALES_RETURN",
            gstin=resolve_series_gstin(
                sales_return.company, getattr(invoice, "company_gstin", None)
            ),
            on_date=sales_return.return_date,
        )
        sales_return.status = SalesReturn.Status.COMPLETED
        sales_return.completed_at = timezone.now()
        sales_return.updated_by = user
        sales_return.save()

        cogs_rev = CogsService.restore_return_stock_and_cogs(sales_return, invoice, items, user)

        now_returned = ReturnService.returned_quantities(invoice)
        fully_returned = all(
            now_returned.get(pid, Decimal("0")) >= qty for pid, qty in sold.items()
        )
        if fully_returned and invoice.status != SalesInvoice.Status.RETURNED:
            invoice.status = SalesInvoice.Status.RETURNED
            invoice.save(update_fields=["status"])

        existing_linked = SalesCreditNote.objects.filter(
            sales_return=sales_return,
            status=SalesCreditNote.Status.COMPLETED,
        ).exists()
        if not existing_linked:
            marker = f"AUTO_RETURN:{sales_return.pk}"
            inv_taxable = Decimal(str(invoice.taxable_total or 0))
            ret_taxable = sum(
                (Decimal(str(getattr(it, "taxable_amount", 0) or 0)) for it in items),
                Decimal("0"),
            )
            ratio = Decimal("1")
            if inv_taxable > 0 and not fully_returned:
                ratio = min(Decimal("1"), ret_taxable / inv_taxable)
            note = SalesCreditNote.objects.create(
                company=sales_return.company,
                customer=sales_return.customer,
                sales_invoice=invoice,
                sales_return=sales_return,
                note_date=sales_return.return_date,
                reason=NoteReason.SALES_RETURN,
                reason_detail=f"Auto from sales return {sales_return.number} [{marker}]",
                invoice_discount=(Decimal(str(invoice.invoice_discount or 0)) * ratio).quantize(Decimal("0.01")),
                invoice_discount_mode=invoice.invoice_discount_mode,
                auto_round_off=invoice.auto_round_off if fully_returned else False,
                created_by=user,
                updated_by=user,
            )
            note.additional_charges = Decimal("0.00") if not fully_returned else Decimal(str(invoice.additional_charges or 0))
            inv_items_by_product = {}
            for inv_item in invoice.items.all():
                inv_items_by_product.setdefault(inv_item.product_id, inv_item)
            items_data = [
                {
                    "product": item.product,
                    "description": getattr(item, "description", "") or "",
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "discount_percent": item.discount_percent,
                    "gst_rate": item.gst_rate,
                    "cess_rate": (
                        getattr(inv_items_by_product.get(item.product_id), "cess_rate", Decimal("0"))
                        if inv_items_by_product.get(item.product_id) is not None
                        else Decimal(str(getattr(item, "cess_rate", 0) or 0))
                    ),
                    "source_item": inv_items_by_product.get(item.product_id),
                }
                for item in items
            ]
            from .notes_services import SalesNotesService

            SalesNotesService.set_credit_note_items(note, items_data, user)
            SalesNotesService.complete_credit_note(note, user)

        if sales_return.company.accounting_enabled:
            from accounting.services import PostingService

            PostingService.post_sales_return_cogs(sales_return, cogs_rev, user)

        emit("document.completed", document=sales_return, user=user, event="sales_return.completed")
        return sales_return

    @staticmethod
    @transaction.atomic
    def cancel_return(sales_return: SalesReturn, user):
        sales_return = SalesReturn.objects.select_for_update().get(pk=sales_return.pk)
        from reporting.gst_periods import assert_period_allows_money_amend

        assert_period_allows_money_amend(
            sales_return.company, sales_return.return_date, allow_soft_closed=True
        )
        if sales_return.status == SalesReturn.Status.CANCELLED:
            raise BusinessRuleError("Return is already cancelled.")
        if sales_return.status == SalesReturn.Status.COMPLETED:
            return_moves = list(
                StockMovement.objects.filter(
                    company=sales_return.company,
                    movement_type=MovementType.SALES_RETURN,
                    reference_type="sales_return",
                    reference_id=str(sales_return.pk),
                )
            )
            if return_moves:
                for move in return_moves:
                    InventoryService.post_movement(
                        company=sales_return.company,
                        warehouse=move.warehouse,
                        product=move.product,
                        batch=move.batch,
                        movement_type=MovementType.ADJUSTMENT,
                        quantity=-abs(Decimal(str(move.quantity))),
                        unit_cost=move.unit_cost,
                        reference_type="sales_return_cancel",
                        reference_id=sales_return.pk,
                        reason=f"Cancellation of {sales_return.number}",
                        user=user,
                    )
            else:
                for item in sales_return.items.select_related("product"):
                    InventoryService.post_movement(
                        company=sales_return.company,
                        warehouse=sales_return.sales_invoice.warehouse,
                        product=item.product,
                        movement_type=MovementType.ADJUSTMENT,
                        quantity=-item.quantity,
                        reference_type="sales_return_cancel",
                        reference_id=sales_return.pk,
                        reason=f"Cancellation of {sales_return.number}",
                        user=user,
                    )
            invoice = sales_return.sales_invoice
            from inventory.models import SerialNumber
            from inventory.services import SerialNumberService

            for item in sales_return.items.select_related("product"):
                if item.product.track_serial and item.serial_numbers:
                    SerialNumberService.transition(
                        company=sales_return.company,
                        product=item.product,
                        warehouse=invoice.warehouse,
                        numbers=item.serial_numbers,
                        quantity=item.quantity,
                        source=SerialNumber.Status.AVAILABLE,
                        target=SerialNumber.Status.SOLD,
                        user=user,
                    )
            if invoice.status == SalesInvoice.Status.RETURNED:
                invoice.status = SalesInvoice.Status.COMPLETED
                invoice.save(update_fields=["status"])
            from .notes_services import SalesNotesService
            from .models import SalesCreditNote as SCN

            for note in SCN.objects.filter(
                sales_return=sales_return,
                status=SCN.Status.COMPLETED,
            ).select_for_update():
                SalesNotesService.cancel_credit_note(note, user)
            if sales_return.company.accounting_enabled:
                from accounting.models import JournalEntry
                from accounting.services import PostingService

                for entry in JournalEntry.objects.filter(
                    company=sales_return.company,
                    source_type="SALES_RETURN",
                    source_id=sales_return.id,
                    purpose="COGS_REVERSE",
                    status=JournalEntry.Status.POSTED,
                ):
                    PostingService.reverse(entry, user, sales_return.return_date)
        sales_return.status = SalesReturn.Status.CANCELLED
        sales_return.cancelled_at = timezone.now()
        sales_return.updated_by = user
        sales_return.save()
        emit("document.cancelled", document=sales_return, user=user, event="sales_return.cancelled")
        return sales_return