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
from .notes_services import _invoice_intra_state
from inventory.models import MovementType, StockMovement
from inventory.services import InventoryService

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
            intra_state=_invoice_intra_state(sales_return.sales_invoice),
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
        items = list(sales_return.items.select_related("product", "product__alternate_unit"))
        if not items:
            raise BusinessRuleError("Cannot complete a return without line items.")

        sold_lines = list(invoice.items.order_by("id"))
        remaining_by_line = {row.id: Decimal(str(row.quantity)) for row in sold_lines}
        lines_by_product = defaultdict(list)
        for row in sold_lines:
            lines_by_product[row.product_id].append(row.id)

        def _consume_prior(exclude=None):
            qs = SalesReturnItem.objects.filter(
                sales_return__sales_invoice=invoice,
                sales_return__status=SalesReturn.Status.COMPLETED,
            ).order_by("id")
            if exclude is not None:
                qs = qs.exclude(sales_return=exclude)
            for prior in qs:
                need = Decimal(str(prior.quantity))
                for lid in lines_by_product.get(prior.product_id, []):
                    if need <= 0:
                        break
                    take = min(need, remaining_by_line[lid])
                    remaining_by_line[lid] -= take
                    need -= take
                if need > 0:
                    raise BusinessRuleError(
                        "Prior returns exceed invoice quantity for this product; repair the return history."
                    )

        _consume_prior(exclude=sales_return)
        source_by_return_item = {}
        for item in items:
            need = Decimal(str(item.quantity))
            matched = None
            for lid in lines_by_product.get(item.product_id, []):
                if need <= 0:
                    break
                avail = remaining_by_line[lid]
                if avail <= 0:
                    continue
                take = min(need, avail)
                remaining_by_line[lid] -= take
                need -= take
                if matched is None:
                    matched = lid
            if need > 0:
                raise BusinessRuleError(
                    f"Return quantity for '{item.product.name}' exceeds remaining returnable quantity on matching invoice lines."
                )
            source_by_return_item[item.pk] = matched

        sold = {
            row["product"]: row["total"]
            for row in invoice.items.values("product").annotate(total=Sum("quantity"))
        }

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
            note.additional_charges = (Decimal(str(invoice.additional_charges or 0)) * ratio).quantize(Decimal("0.01"))
            note.charges_hsn = getattr(invoice, "charges_hsn", "") or ""
            note.charges_gst_rate = getattr(invoice, "charges_gst_rate", Decimal("0")) or Decimal("0")
            note.save(update_fields=["additional_charges", "charges_hsn", "charges_gst_rate"])
            inv_items_by_id = {inv_item.id: inv_item for inv_item in invoice.items.all()}
            items_data = [
                {
                    "product": item.product,
                    "description": getattr(item, "description", "") or "",
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "discount_percent": item.discount_percent,
                    "gst_rate": item.gst_rate,
                    "cess_rate": (
                        getattr(inv_items_by_id.get(source_by_return_item.get(item.pk)), "cess_rate", Decimal("0"))
                        if source_by_return_item.get(item.pk)
                        else Decimal(str(getattr(item, "cess_rate", 0) or 0))
                    ),
                    "cess_amount": (
                        getattr(inv_items_by_id.get(source_by_return_item.get(item.pk)), "cess_amount", Decimal("0"))
                        if source_by_return_item.get(item.pk)
                        else Decimal(str(getattr(item, "cess_amount", 0) or 0))
                    ),
                    "source_item": inv_items_by_id.get(source_by_return_item.get(item.pk)),
                }
                for item in items
            ]
            from .notes_services import SalesNotesService

            SalesNotesService.set_credit_note_items(note, items_data, user)
            tcs_share = (Decimal(str(getattr(invoice, "tcs_amount", 0) or 0)) * ratio).quantize(Decimal("0.01"))
            if fully_returned:
                tcs_share = Decimal(str(getattr(invoice, "tcs_amount", 0) or 0))
            if tcs_share > 0:
                note.tcs_amount = tcs_share
                note.tcs_in_grand_total = True
                note.grand_total = (Decimal(str(note.grand_total or 0)) + tcs_share).quantize(Decimal("0.01"))
                note.save(update_fields=["grand_total", "tcs_amount", "tcs_in_grand_total"])
            SalesNotesService.complete_credit_note(note, user)

        if sales_return.company.accounting_enabled:
            from accounting.services import PostingService

            PostingService.post_sales_return_cogs(sales_return, cogs_rev, user)
            damaged_qty = sum(
                (
                    Decimal(str(item.quantity or 0))
                    for item in items
                    if getattr(item, "condition", "SELLABLE") == "DAMAGED"
                ),
                Decimal("0"),
            )
            if damaged_qty > 0:
                scrap_share = (
                    (cogs_rev * damaged_qty / sum((Decimal(str(i.quantity or 0)) for i in items), Decimal("0"))).quantize(
                        Decimal("0.01")
                    )
                    if items
                    else cogs_rev
                )
                PostingService.post_sales_return_scrap(sales_return, scrap_share, user)

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
            damaged_moves = list(
                StockMovement.objects.filter(
                    company=sales_return.company,
                    movement_type=MovementType.ADJUSTMENT,
                    reference_type="sales_return_damaged",
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
            if damaged_moves:
                for move in damaged_moves:
                    InventoryService.post_movement(
                        company=sales_return.company,
                        warehouse=move.warehouse,
                        product=move.product,
                        batch=move.batch,
                        movement_type=MovementType.ADJUSTMENT,
                        quantity=abs(Decimal(str(move.quantity))),
                        unit_cost=move.unit_cost,
                        reference_type="sales_return_damaged_cancel",
                        reference_id=sales_return.pk,
                        reason=f"Restore damaged scrap of {sales_return.number}",
                        user=user,
                    )
            if not return_moves and not damaged_moves:
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
                    damaged = getattr(item, "condition", "SELLABLE") == "DAMAGED"
                    SerialNumberService.transition(
                        company=sales_return.company,
                        product=item.product,
                        warehouse=invoice.warehouse,
                        numbers=item.serial_numbers,
                        quantity=item.quantity,
                        source=SerialNumber.Status.SCRAPPED if damaged else SerialNumber.Status.AVAILABLE,
                        target=SerialNumber.Status.SOLD,
                        user=user,
                    )
            if invoice.status == SalesInvoice.Status.RETURNED:
                from .models import SalesReturn as SR

                other_open = SR.objects.filter(
                    sales_invoice=invoice,
                    status=SR.Status.COMPLETED,
                ).exclude(pk=sales_return.pk).exists()
                if not other_open:
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