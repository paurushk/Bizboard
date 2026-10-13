"""Sales return lifecycle — extracted from SalesService (BB-000476)."""

from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.events import emit
from core.services.audit import record_document_event
from core.exceptions import BusinessRuleError
from core.services.tax_engine.registry import get_tax_engine
from core.services.document_numbers import DocumentNumberService, resolve_series_gstin
from .notes_services import _invoice_intra_state
from inventory.models import MovementType, StockMovement
from inventory.services import InventoryService

from .models import (
    NoteReason,
    SalesCreditNote,
    SalesCreditNoteItem,
    SalesInvoice,
    SalesReturn,
    SalesReturnItem,
)
from .services import _build_items, _tax_enabled, _validate_lines


class ReturnService:
    @staticmethod
    @transaction.atomic
    def set_return_items(sales_return: SalesReturn, items_data, user, *, validate_serials=True):
        if sales_return.status != SalesReturn.Status.DRAFT:
            raise BusinessRuleError("Completed return cannot be edited.")
        _validate_lines(items_data, sales_return.company, check_active=False)
        for line in items_data:
            product = line["product"]
            if validate_serials and getattr(product, "track_serial", False):
                serial_numbers = line.get("serial_numbers") or []
                numbers = [str(n).strip() for n in serial_numbers if str(n).strip()]
                if len(numbers) != int(Decimal(str(line["quantity"]))):
                    raise BusinessRuleError(
                        f"Exactly {line['quantity']} serial number(s) are required for "
                        f"tracked product '{product.name}'.",
                        code="serial_required",
                    )
        sales_return.items.all().delete()
        items = _build_items(SalesReturnItem, "sales_return", sales_return, items_data)
        if sales_return.sales_invoice_id:
            SalesInvoice.objects.select_for_update().get(
                pk=sales_return.sales_invoice_id, company_id=sales_return.company_id
            )
        get_tax_engine(sales_return.company).compute_document_totals(
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
    def _take_from(remaining, need, lids, *, overflow):
        taken = []
        for lid in lids:
            if need <= 0:
                break
            if lid not in remaining:
                raise BusinessRuleError("source_item does not belong to this invoice.")
            avail = remaining[lid]
            if avail <= 0:
                continue
            take = min(need, avail)
            remaining[lid] -= take
            need -= take
            taken.append((lid, take))
        if need > 0:
            raise BusinessRuleError(overflow)
        return taken

    @staticmethod
    def line_state(invoice, exclude_return=None):
        """Per invoice line: sold, returned (completed returns) and credited by
        standalone credit notes (SRF-06). One source of truth for the complete
        path, the returnable-lines endpoint and the totals preview."""
        sold_lines = list(invoice.items.order_by("id"))
        sold = {row.id: Decimal(str(row.quantity)) for row in sold_lines}
        remaining = dict(sold)
        lines_by_product = defaultdict(list)
        for row in sold_lines:
            lines_by_product[row.product_id].append(row.id)

        prior_qs = SalesReturnItem.objects.filter(
            sales_return__sales_invoice=invoice,
            sales_return__status=SalesReturn.Status.COMPLETED,
        ).order_by("id")
        if exclude_return is not None:
            prior_qs = prior_qs.exclude(sales_return=exclude_return)
        returned_serials = defaultdict(list)
        for prior in prior_qs:
            need = Decimal(str(prior.quantity))
            if prior.source_item_id:
                lids = [prior.source_item_id]
                overflow = "Prior returns exceed the named invoice line; repair the return history."
            else:
                lids = lines_by_product.get(prior.product_id, [])
                overflow = (
                    "Prior returns exceed invoice quantity for this product; repair the return history."
                )
            ReturnService._take_from(remaining, need, lids, overflow=overflow)
            if lids and prior.serial_numbers:
                returned_serials[lids[0]].extend(str(n) for n in prior.serial_numbers)
        after_returns = dict(remaining)

        # SRF-06: units already credited by a standalone (non return-linked)
        # credit note are not returnable either.
        standalone = defaultdict(Decimal)
        standalone_notes = defaultdict(list)
        cn_rows = SalesCreditNoteItem.objects.filter(
            credit_note__sales_invoice=invoice,
            credit_note__status=SalesCreditNote.Status.COMPLETED,
            credit_note__sales_return__isnull=True,
            source_item__isnull=False,
        ).values_list("source_item_id", "quantity", "credit_note__number")
        for lid, qty, number in cn_rows:
            if lid not in remaining:
                continue
            q = Decimal(str(qty or 0))
            standalone[lid] += q
            if number and number not in standalone_notes[lid]:
                standalone_notes[lid].append(number)
            remaining[lid] = max(Decimal("0"), remaining[lid] - q)
        return {
            "sold": sold,
            "remaining": remaining,
            "after_returns": after_returns,
            "lines_by_product": lines_by_product,
            "standalone": standalone,
            "standalone_notes": standalone_notes,
            "returned_serials": returned_serials,
        }

    @staticmethod
    def returnable_lines(invoice):
        rows = []
        state = ReturnService.line_state(invoice)
        for row in invoice.items.select_related("product").order_by("id"):
            sold = state["sold"][row.id]
            standalone = state["standalone"].get(row.id, Decimal("0"))
            returned = sold - state["after_returns"][row.id]
            rows.append({
                "source_item": row.id,
                "product": row.product_id,
                "product_name": row.product.name,
                "sold": sold,
                "returned": returned,
                "credited_standalone": standalone,
                "returnable": state["remaining"][row.id],
                "returned_serials": state["returned_serials"].get(row.id, []),
            })
        return rows

    @staticmethod
    def _standalone_hint(state, lids):
        for lid in lids:
            qty = state["standalone"].get(lid)
            if qty:
                notes = ", ".join(state["standalone_notes"].get(lid, [])) or "a credit note"
                return (
                    f" Credit note(s) {notes} already credited {qty.normalize():f} unit(s) on "
                    f"this invoice line, so only {state['remaining'][lid].normalize():f} can still be returned."
                )
        return ""

    @staticmethod
    def plan_takes(items, state):
        """Match each return line to invoice lines and enforce headroom."""
        remaining = dict(state["remaining"])
        lines_by_product = state["lines_by_product"]
        source_takes = []
        for item in items:
            need = Decimal(str(item.quantity))
            if item.source_item_id:
                if item.source_item is not None and item.source_item.product_id != item.product_id:
                    raise BusinessRuleError("source_item product does not match the return line.")
                lids = [item.source_item_id]
                overflow = (
                    f"Return quantity for '{item.product.name}' exceeds the remaining "
                    "quantity on the named invoice line."
                )
            else:
                lids = lines_by_product.get(item.product_id, [])
                if len(lids) > 1:
                    raise BusinessRuleError(
                        "Return lines must name the invoice line (source_item) when "
                        "the same product is on more than one line."
                    )
                overflow = (
                    f"Return quantity for '{item.product.name}' exceeds remaining "
                    "returnable quantity on matching invoice lines."
                )
            overflow += ReturnService._standalone_hint(state, lids)
            for lid, take in ReturnService._take_from(remaining, need, lids, overflow=overflow):
                source_takes.append((item, lid, take))
        return source_takes

    @staticmethod
    def is_fully_returned(invoice, exclude_return=None, extra_takes=None):
        """True when nothing on the invoice can still be returned.

        Units credited by a standalone credit note count as spent, so an invoice
        that was part-credited and then fully returned does flip to RETURNED, and
        cancelling one of two returns puts it back (``exclude_return``).
        ``extra_takes`` is a list of ``(item, line_id, qty)`` not yet saved.
        """
        state = ReturnService.line_state(invoice, exclude_return=exclude_return)
        left = dict(state["remaining"])
        for _item, lid, take in extra_takes or []:
            left[lid] = left.get(lid, Decimal("0")) - take
        return all(v <= 0 for v in left.values())

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
    def preview_totals(company, customer, invoice, return_date, items_data, user):
        """Exact totals of the credit note this return would issue (SRF-11).

        Runs the real draft -> plan -> credit-note-build path inside a savepoint
        and rolls everything back, so nothing (rows, numbers, stock) persists.
        """
        # An explicit atomic block, forced to roll back: a bare savepoint does
        # nothing when the request is not already inside a transaction, which
        # left the preview's draft return and credit note behind.
        with transaction.atomic():
            try:
                return ReturnService._preview_in_transaction(
                    company, customer, invoice, return_date, items_data, user
                )
            finally:
                transaction.set_rollback(True)

    @staticmethod
    def _preview_in_transaction(company, customer, invoice, return_date, items_data, user):
        sales_return = SalesReturn.objects.create(
            company=company,
            customer=customer,
            sales_invoice=invoice,
            return_date=return_date,
            created_by=user,
            updated_by=user,
        )
        ReturnService.set_return_items(
            sales_return, [dict(line) for line in items_data], user, validate_serials=False
        )
        items = list(
            sales_return.items.select_related("product", "product__alternate_unit", "source_item")
        )
        if not items:
            raise BusinessRuleError("Select at least one line to preview.")
        state = ReturnService.line_state(invoice)
        source_takes = ReturnService.plan_takes(items, state)
        fully_returned = ReturnService.is_fully_returned(invoice, extra_takes=source_takes)
        note = ReturnService.build_credit_note_draft(
            sales_return, invoice, items, source_takes, fully_returned, user
        )
        note.refresh_from_db()
        return {
            "line_count": len(items),
            "units": sum((Decimal(str(i.quantity)) for i in items), Decimal("0")),
            "taxable_total": note.taxable_total,
            "cgst_total": note.cgst_total,
            "sgst_total": note.sgst_total,
            "igst_total": note.igst_total,
            "cess_total": getattr(note, "cess_total", Decimal("0")),
            "invoice_discount": note.invoice_discount,
            "additional_charges": note.additional_charges,
            "tcs_amount": note.tcs_amount,
            "round_off": note.round_off,
            "grand_total": note.grand_total,
            "fully_returned": fully_returned,
        }

    @staticmethod
    def build_credit_note_draft(sales_return, invoice, items, source_takes, fully_returned, user):
        """Create the (uncompleted) credit note a return issues. Shared by
        complete_return and the totals preview so the preview is exact."""
        marker = f"AUTO_RETURN:{sales_return.pk}"
        inv_taxable = Decimal(str(invoice.taxable_total or 0))
        ret_taxable = sum(
            (Decimal(str(getattr(it, "taxable_amount", 0) or 0)) for it in items),
            Decimal("0"),
        )
        ratio = Decimal("1")
        if inv_taxable > 0 and not fully_returned:
            ratio = min(Decimal("1"), ret_taxable / inv_taxable)
        elif not fully_returned:
            # B2-003: SalesReturnItem is a DocumentLineModel — it has
            # `line_total` / `taxable_amount`, not `grand_total` (that lives
            # on the header). Reading `it.grand_total` raised AttributeError
            # for a partial return of a fully NIL/exempt invoice.
            inv_grand = Decimal(str(invoice.grand_total or 0))
            ret_grand = sum(
                (
                    Decimal(str(
                        getattr(it, "line_total", 0)
                        or getattr(it, "taxable_amount", 0)
                        or 0
                    ))
                    for it in items
                ),
                Decimal("0"),
            )
            ratio = min(Decimal("1"), ret_grand / inv_grand) if inv_grand > 0 else Decimal("0")
        inv_discount = Decimal(str(invoice.invoice_discount or 0))
        inv_charges = Decimal(str(invoice.additional_charges or 0))
        inv_tcs = Decimal(str(getattr(invoice, "tcs_amount", 0) or 0))
        # Every earlier completed credit note (return-linked or standalone) has
        # already relieved its share of discount / charges / TCS.
        prior_qs = SalesCreditNote.objects.filter(
            sales_invoice=invoice,
            status=SalesCreditNote.Status.COMPLETED,
        ).exclude(sales_return=sales_return)
        if fully_returned:
            prior_d = prior_qs.aggregate(d=Sum("invoice_discount"))["d"] or Decimal("0")
            prior_c = prior_qs.aggregate(c=Sum("additional_charges"))["c"] or Decimal("0")
            prior_t = prior_qs.aggregate(t=Sum("tcs_amount"))["t"] or Decimal("0")
            discount_share = (inv_discount - prior_d).quantize(Decimal("0.01"))
            charges_share = (inv_charges - prior_c).quantize(Decimal("0.01"))
            tcs_share = (inv_tcs - prior_t).quantize(Decimal("0.01"))
        else:
            discount_share = (inv_discount * ratio).quantize(Decimal("0.01"))
            charges_share = (inv_charges * ratio).quantize(Decimal("0.01"))
            tcs_share = (inv_tcs * ratio).quantize(Decimal("0.01"))
        note = SalesCreditNote.objects.create(
            company=sales_return.company,
            customer=sales_return.customer,
            sales_invoice=invoice,
            sales_return=sales_return,
            note_date=sales_return.return_date,
            reason=NoteReason.SALES_RETURN,
            reason_detail=f"Auto from sales return {sales_return.number} [{marker}]",
            invoice_discount=max(Decimal("0"), discount_share),
            invoice_discount_mode=invoice.invoice_discount_mode,
            auto_round_off=invoice.auto_round_off if fully_returned else False,
            created_by=user,
            updated_by=user,
        )
        note.additional_charges = max(Decimal("0"), charges_share)
        note.charges_hsn = getattr(invoice, "charges_hsn", "") or ""
        note.charges_gst_rate = getattr(invoice, "charges_gst_rate", Decimal("0")) or Decimal("0")
        note.save(update_fields=["additional_charges", "charges_hsn", "charges_gst_rate"])
        inv_items_by_id = {inv_item.id: inv_item for inv_item in invoice.items.all()}
        items_data = []
        for item, lid, take in source_takes:
            src = inv_items_by_id.get(lid)
            src_qty = Decimal(str(src.quantity)) if src else Decimal("0")
            cess_full = (
                Decimal(str(getattr(src, "cess_amount", 0) or 0))
                if src
                else Decimal(str(getattr(item, "cess_amount", 0) or 0))
            )
            cess_scaled = (
                (cess_full * take / src_qty).quantize(Decimal("0.01"))
                if src_qty
                else cess_full
            )
            items_data.append({
                "product": item.product,
                "description": getattr(item, "description", "") or "",
                "quantity": take,
                "unit_price": item.unit_price,
                "discount_percent": item.discount_percent,
                "gst_rate": item.gst_rate,
                "cess_rate": (
                    getattr(src, "cess_rate", Decimal("0")) if src else Decimal(str(getattr(item, "cess_rate", 0) or 0))
                ),
                "cess_amount": cess_scaled,
                "source_item": src,
            })
        from .notes_services import SalesNotesService

        # R-006: set_credit_note_items applies RCM memo when the source
        # invoice is reverse-charge so the auto-CN grand_total excludes GST.
        SalesNotesService.set_credit_note_items(note, items_data, user)
        if tcs_share > 0:
            note.tcs_amount = tcs_share
            note.tcs_in_grand_total = True
            note.grand_total = (Decimal(str(note.grand_total or 0)) + tcs_share).quantize(Decimal("0.01"))
            note.save(update_fields=["grand_total", "tcs_amount", "tcs_in_grand_total"])
        if fully_returned:
            # A full return must relieve the same rupees the invoice charged.
            # Fold TCS in first. Recomputing tax can still leave the note
            # up to ₹1 off the rounded invoice; that remainder goes into round-off.
            target = Decimal(str(invoice.grand_total or 0))
            current = Decimal(str(note.grand_total or 0))
            gap = (target - current).quantize(Decimal("0.01"))
            if gap != 0 and abs(gap) <= Decimal("1.00"):
                note.round_off = (Decimal(str(note.round_off or 0)) + gap).quantize(Decimal("0.01"))
                note.grand_total = target
                note.save(update_fields=["round_off", "grand_total", "updated_at"])
        return note

    @staticmethod
    @transaction.atomic
    def complete_return(sales_return: SalesReturn, user, *, gst_guard_override_reason=None):
        from .cogs_service import CogsService

        sales_return = SalesReturn.objects.select_for_update().get(pk=sales_return.pk)
        from reporting.gst_periods import assert_period_allows_money_amend

        assert_period_allows_money_amend(sales_return.company, sales_return.return_date)
        if sales_return.status != SalesReturn.Status.DRAFT:
            raise BusinessRuleError(f"Cannot complete a return in status {sales_return.status}.")
        # CR-014: lock source invoice before remaining-qty headroom check.
        invoice = SalesInvoice.objects.select_for_update().get(
            pk=sales_return.sales_invoice_id,
            company_id=sales_return.company_id,
        )
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
        items = list(
            sales_return.items.select_related("product", "product__alternate_unit", "source_item")
        )
        if not items:
            raise BusinessRuleError("Cannot complete a return without line items.")

        state = ReturnService.line_state(invoice, exclude_return=sales_return)
        source_takes = ReturnService.plan_takes(items, state)

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

        try:
            fully_returned = ReturnService.is_fully_returned(invoice)
        except BusinessRuleError:
            # Inconsistent legacy history: fall back to the plain per-product sums.
            now_returned = ReturnService.returned_quantities(invoice)
            fully_returned = all(
                now_returned.get(pid, Decimal("0")) >= qty for pid, qty in sold.items()
            )
        if fully_returned and invoice.status != SalesInvoice.Status.RETURNED:
            invoice.status = SalesInvoice.Status.RETURNED
            invoice.save(update_fields=["status"])
            from reporting.invoice_profit_service import InvoiceProfitService
            from sales.public_links import revoke_invoice_public_links

            InvoiceProfitService.sync_status(invoice)
            revoke_invoice_public_links(invoice)

        existing_linked = SalesCreditNote.objects.filter(
            sales_return=sales_return,
            status=SalesCreditNote.Status.COMPLETED,
        ).exists()
        if not existing_linked:
            note = ReturnService.build_credit_note_draft(
                sales_return, invoice, items, source_takes, fully_returned, user
            )
            from .notes_services import SalesNotesService

            # CR-124: a return against a paid invoice must not silently override
            # payment allocations. confirm_paid_invoice=True routes through
            # complete_credit_note's single auto-unallocate pass (receipt money
            # up to the CN amount → unallocated customer advance), instead of
            # duplicating that logic here or hard-failing the whole return.
            SalesNotesService.complete_credit_note(
                note,
                user,
                confirm_paid_invoice=True,
                confirm_price_override=True,
                gst_guard_override_reason=gst_guard_override_reason,
            )

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
                damaged_cogs = getattr(sales_return, "_damaged_cogs_rev", None)
                if damaged_cogs is not None:
                    scrap_share = damaged_cogs
                else:
                    scrap_share = (
                        (cogs_rev * damaged_qty / sum((Decimal(str(i.quantity or 0)) for i in items), Decimal("0"))).quantize(
                            Decimal("0.01")
                        )
                        if items
                        else cogs_rev
                    )
                if scrap_share > 0:
                    PostingService.post_sales_return_scrap(sales_return, scrap_share, user)

        record_document_event(document=sales_return, user=user, event="sales_return.completed")
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
                from .cogs_service import CogsService

                invoice_for_lots = sales_return.sales_invoice
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
                    # N-002: reverse the peels that complete restored, don't skip FIFO.
                    # Returns made since per-layer detail was recorded undo exactly
                    # what they put back; older ones use the approximation below.
                    remaining = abs(Decimal(str(move.quantity)))
                    if InventoryService.unrestore_from_detail(move):
                        remaining = Decimal("0")
                    if remaining > 0 and invoice_for_lots is not None:
                        candidates = CogsService.invoice_sale_moves(
                            invoice_for_lots, product=move.product
                        )
                        # Returns from before per-layer detail existed: at least restrict
                        # to the sale movements of the invoice lines the return named.
                        named: list = []
                        for ritem in sales_return.items.filter(product=move.product, source_item__isnull=False):
                            line_moves, _mode, _keys = CogsService.line_sale_moves(
                                invoice_for_lots, ritem, candidates
                            )
                            if _mode:
                                named.extend(m for m in line_moves if m not in named)
                        if named:
                            candidates = named
                        if move.reason and move.reason.startswith("SALE_LINE:"):
                            tagged = [c for c in candidates if c.reason == move.reason]
                            if tagged:
                                candidates = tagged
                        elif move.reason and move.reason.startswith("SALE_MOVE:"):
                            exact = [c for c in candidates if f"SALE_MOVE:{c.pk}" == move.reason]
                            if exact:
                                candidates = exact
                        for sale_move in candidates:
                            if remaining <= 0:
                                break
                            if move.batch_id and sale_move.batch_id != move.batch_id:
                                continue
                            take = min(remaining, abs(Decimal(str(sale_move.quantity))))
                            InventoryService.unrestore_fifo_peels(sale_move, take)
                            remaining -= take
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
                raise BusinessRuleError(
                    "Cannot cancel this sales return: original stock movements are missing. "
                    "Restore stock with a manual adjustment instead of inventing unbatched quantity."
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
                from .models import SalesInvoice as SI
                from .models import SalesReturn as SR

                # CR-095: lock invoice before other_open check + status flip.
                invoice = SI.objects.select_for_update().get(
                    pk=invoice.pk,
                    company_id=sales_return.company_id,
                )
                try:
                    still_fully_returned = ReturnService.is_fully_returned(
                        invoice, exclude_return=sales_return
                    )
                except BusinessRuleError:
                    still_fully_returned = SR.objects.filter(
                        sales_invoice=invoice, status=SR.Status.COMPLETED
                    ).exclude(pk=sales_return.pk).exists()
                if not still_fully_returned and invoice.status == SI.Status.RETURNED:
                    invoice.status = SI.Status.COMPLETED
                    invoice.save(update_fields=["status"])
                    from reporting.invoice_profit_service import InvoiceProfitService

                    InvoiceProfitService.sync_status(invoice)
            # Mark the return CANCELLED first so `cancel_credit_note`'s
            # "cancel the sales return instead" guard (active only while the
            # return is COMPLETED) does not block this flow.
            sales_return.status = SalesReturn.Status.CANCELLED
            sales_return.cancelled_at = timezone.now()
            sales_return.updated_by = user
            sales_return.save(
                update_fields=["status", "cancelled_at", "updated_by", "updated_at"]
            )

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
                    purpose__in=("COGS_REVERSE", "DAMAGED_SCRAP"),
                    status=JournalEntry.Status.POSTED,
                ):
                    PostingService.reverse(entry, user, sales_return.return_date)
        sales_return.status = SalesReturn.Status.CANCELLED
        sales_return.cancelled_at = timezone.now()
        sales_return.updated_by = user
        sales_return.save()
        record_document_event(document=sales_return, user=user, event="sales_return.cancelled")
        emit("document.cancelled", document=sales_return, user=user, event="sales_return.cancelled")
        return sales_return