"""Sales credit/debit notes, orders, and delivery challans (Phase 1 / 1.5)."""

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from core.events import emit
from core.services.audit import record_document_event
from core.exceptions import BusinessRuleError, raise_confirm_required
from core.help_codes import HelpCode
from core.services.billing import apply_rcm_memo_after_tax
from core.services.tax_engine.registry import get_tax_engine
from core.services.document_numbers import DocumentNumberService, resolve_series_gstin
from core.services.place_of_supply import assert_place_of_supply_for_gst, party_intra_state
from masters.models import Customer, Product

from .models import (
    DeliveryChallan,
    DeliveryChallanItem,
    NoteReason,
    SalesCreditNote,
    SalesCreditNoteItem,
    SalesDebitNote,
    SalesDebitNoteItem,
    SalesInvoice,
    SalesOrder,
    SalesOrderItem,
)
from .services import SalesService, _build_items, _tax_enabled, _validate_lines
from .status_semantics import OPEN_RECEIVABLE_STATUSES


def _single_active_company_gstin(company):
    from accounts.models import CompanyGstin

    active = list(
        CompanyGstin.objects.filter(company=company, is_active=True).order_by("-is_primary", "id")
    )
    return active[0] if len(active) == 1 else None


def _resolve_product(line, company):
    product = line.get("product")
    if isinstance(product, Product):
        return product
    return Product.objects.get(pk=product, company=company)


def _normalize_items(items_data, company):
    out = []
    for line in items_data:
        d = dict(line)
        d["product"] = _resolve_product(d, company)
        out.append(d)
    return out


def _invoice_intra_state(inv) -> bool:
    """BB-000649: freeze intra/inter from the source invoice tax split."""
    if Decimal(str(inv.igst_total or 0)) > 0:
        return False
    if Decimal(str(inv.cgst_total or 0)) + Decimal(str(inv.sgst_total or 0)) > 0:
        return True
    return party_intra_state(inv.company, inv.customer.state, inv.customer.gstin or "", supply_type=getattr(inv, "supply_type", ""))


def _apply_rcm_memo_if_linked(note, items) -> None:
    """R-006: if the linked sales invoice is reverse-charge, the note's value
    legs must also be RCM (memo taxable/tax, zero GST on the note itself)
    so grand_total excludes GST — same two-pass as purchases notes.
    SalesCreditNote/SalesDebitNote have no is_reverse_charge column of
    their own — set it transiently so apply_rcm_memo_after_tax applies.
    """
    invoice = getattr(note, "sales_invoice", None)
    note.is_reverse_charge = bool(invoice and getattr(invoice, "is_reverse_charge", False))
    if note.is_reverse_charge:
        apply_rcm_memo_after_tax(note, items)


def _check_note_hsn(note, inv, kind: str, warnings: list) -> None:
    """DEP-05: HSN is mandatory for e-invoice companies and for standalone B2B (GSTIN) notes —
    the GSTR-1 HSN summary (Table 12) cannot be built without it. B2C notes, and the credit
    note a sales return issues, only warn."""
    missing_hsn = note.items.filter(hsn_code="").count()
    if not missing_hsn:
        return
    party_gstin = getattr(inv, "filing_party_gstin", None) or getattr(inv.customer, "gstin", "") or ""
    # The credit note a sales return issues must never block taking goods back:
    # for it, only an e-invoice company is refused; everyone else gets the warning.
    from_return = getattr(note, "sales_return_id", None) is not None
    if getattr(note.company, "einvoice_enabled", False) or (party_gstin.strip() and not from_return):
        raise BusinessRuleError(
            f"{missing_hsn} line(s) missing HSN — required before completing a {kind} note "
            "for a GST-registered customer or an e-invoice company."
        )
    warnings.append(f"{missing_hsn} line(s) missing HSN — GSTR Table 12 / e-Invoice may fail.")


def _sales_note_headroom(inv, *, exclude_cn_id=None) -> Decimal:
    """BB-000648: creditable value = invoiced − prior CNs + prior DNs (not AR outstanding)."""
    prior_cns = (
        SalesCreditNote.objects.filter(
            sales_invoice=inv, status=SalesCreditNote.Status.COMPLETED
        )
        .exclude(pk=exclude_cn_id)
        .aggregate(total=Sum("grand_total"))["total"]
        or Decimal("0")
    )
    prior_dns = (
        SalesDebitNote.objects.filter(
            sales_invoice=inv, status=SalesDebitNote.Status.COMPLETED
        ).aggregate(total=Sum("grand_total"))["total"]
        or Decimal("0")
    )
    return Decimal(str(inv.grand_total or 0)) - Decimal(str(prior_cns)) + Decimal(str(prior_dns))


def credit_line_uses_goods(reason, note_price, note_discount, src_price, src_discount) -> bool:
    """True when a credit-note line credits the units themselves (Q1 / DEP-02).

    A post-sale discount, or a line credited below the sold net unit price (a rate
    correction), only adjusts the price of goods the customer keeps: it is value-only
    and uses up no returnable quantity. Crediting the full unit price credits the unit.
    """
    from .models import VALUE_ONLY_NOTE_REASONS

    if reason in VALUE_ONLY_NOTE_REASONS:
        return False
    note_net = Decimal(str(note_price or 0)) * (1 - Decimal(str(note_discount or 0)) / 100)
    src_net = Decimal(str(src_price or 0)) * (1 - Decimal(str(src_discount or 0)) / 100)
    return not (src_net > 0 and note_net < src_net - Decimal("0.005"))


def prior_goods_credited_qty(src, *, exclude_note_id=None) -> Decimal:
    """Quantity of ``src`` already credited as goods by completed credit notes."""
    rows = SalesCreditNoteItem.objects.filter(
        credit_note__status=SalesCreditNote.Status.COMPLETED,
        source_item=src,
    )
    if exclude_note_id is not None:
        rows = rows.exclude(credit_note_id=exclude_note_id)
    total = Decimal("0")
    for qty, price, disc, reason in rows.values_list(
        "quantity", "unit_price", "discount_percent", "credit_note__reason"
    ):
        if credit_line_uses_goods(reason, price, disc, src.unit_price, src.discount_percent):
            total += Decimal(str(qty or 0))
    return total


def _restore_peeled_receipt_allocations(note, user):
    """Put receipt slices back on the source invoice after a credit note is cancelled."""
    slices = list(note.peeled_receipt_allocations or [])
    if not slices or not note.sales_invoice_id:
        return
    from ledgers.services import LedgerService
    from payments.models import CustomerReceipt, ReceiptStatus
    from payments.receipt_math import cash_available
    from payments.services import PaymentService

    inv = SalesInvoice.objects.select_for_update().get(
        pk=note.sales_invoice_id, company_id=note.company_id,
    )
    restored = Decimal("0")
    wanted_total = Decimal("0")
    for slice_ in slices:
        wanted_total += Decimal(str(slice_.get("amount") or 0))
        receipt = (
            CustomerReceipt.objects.select_for_update()
            .filter(pk=slice_.get("receipt_id"), company_id=note.company_id)
            .first()
        )
        if receipt is None or receipt.status != ReceiptStatus.POSTED:
            continue
        want = Decimal(str(slice_.get("amount") or 0))
        outstanding = LedgerService.sales_invoice_outstanding(inv)
        unallocated = cash_available(receipt)
        apply_amt = min(want, outstanding, unallocated)
        if apply_amt > 0:
            try:
                with transaction.atomic():
                    PaymentService.allocate_receipt(
                        receipt=receipt, sales_invoice=inv, amount=apply_amt, user=user,
                    )
                restored += apply_amt
            except (BusinessRuleError, IntegrityError):
                # The receipt was allocated to this invoice again while the credit note stood.
                # That slice is already covered; cancelling the note must not fail over it.
                continue
    note.peeled_receipt_allocations = []
    note.save(update_fields=["peeled_receipt_allocations", "updated_at"])
    shortfall = wanted_total - restored
    if shortfall > 0:
        # NEW-06: the advance this note created was refunded or used elsewhere
        # before the note was cancelled, so the invoice is left partly unpaid.
        from core.services.audit import AuditService

        AuditService.log(
            action="credit_note_cancel_partial_restore",
            company=note.company,
            user=user,
            entity_type="SalesCreditNote",
            entity_id=note.pk,
            metadata={"peeled": str(wanted_total), "restored": str(restored), "shortfall": str(shortfall)},
        )


EXCESS_DEBIT_MAX_MULTIPLE = Decimal("3")


class SalesNotesService:
    # ---------- Credit notes ----------

    @staticmethod
    @transaction.atomic
    def set_credit_note_items(note: SalesCreditNote, items_data, user):
        if note.status != SalesCreditNote.Status.DRAFT:
            raise BusinessRuleError("Completed credit note cannot be edited.")
        items_data = _normalize_items(items_data, note.company)
        _validate_lines(items_data, note.company, check_active=False)
        note.items.all().delete()
        items = _build_items(SalesCreditNoteItem, "credit_note", note, items_data)
        for item, src in zip(items, items_data):
            src_item = src.get("source_item", src.get("source_item_id"))
            if src_item is not None:
                item.source_item_id = src_item.pk if hasattr(src_item, "pk") else src_item
        if note.sales_invoice_id:
            inv = SalesInvoice.objects.select_for_update().get(
                pk=note.sales_invoice_id, company_id=note.company_id
            )
        else:
            inv = note.sales_invoice
        get_tax_engine(note.company).compute_document_totals(
            note,
            items,
            tax_enabled=_tax_enabled(inv.invoice_type),
            intra_state=_invoice_intra_state(inv),
            invoice_discount=note.invoice_discount,
            invoice_discount_mode=note.invoice_discount_mode,
            auto_round_off=note.auto_round_off,
            additional_charges=Decimal(str(getattr(note, "additional_charges", 0) or 0)),
        )
        _apply_rcm_memo_if_linked(note, items)
        SalesCreditNoteItem.objects.bulk_create(items)
        note.updated_by = user
        note.save()
        return note

    @staticmethod
    @transaction.atomic
    def complete_credit_note(
        note: SalesCreditNote, user, *, confirm_paid_invoice: bool = False,
        confirm_price_override: bool = False, gst_guard_override_reason=None,
    ):
        # CR-127: lock CN + source invoice with company_id (defense-in-depth).
        note = SalesCreditNote.objects.select_for_update().get(
            pk=note.pk, company_id=note.company_id
        )
        if note.status != SalesCreditNote.Status.DRAFT:
            raise BusinessRuleError(f"Cannot complete credit note in status {note.status}.")
        if not note.items.exists():
            raise BusinessRuleError("Cannot complete a credit note without line items.")
        from reporting.gst_periods import assert_period_allows_money_amend, mark_period_dirty_if_snapshotted

        assert_period_allows_money_amend(note.company, note.note_date)
        # CR-127: lock source invoice with company_id (DN / purchase CN twin).
        inv = SalesInvoice.objects.select_for_update().get(
            pk=note.sales_invoice_id,
            company_id=note.company_id,
        )
        if inv.status not in (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED):
            raise BusinessRuleError("Credit notes require a completed source invoice.")
        if note.note_date and inv.invoice_date and note.note_date < inv.invoice_date:
            raise BusinessRuleError(
                "Credit note date cannot be before the original invoice date."
            )
        # SALES_RETURN CNs must be the auto-CN from SalesReturn.complete (stock lives there).
        if note.reason == NoteReason.SALES_RETURN and note.sales_return_id is None:
            raise BusinessRuleError(
                "Credit notes with reason SALES_RETURN must be linked to a completed sales return. "
                "Stock is restored on the return, not on a standalone credit note."
            )
        assert_place_of_supply_for_gst(
            company=note.company,
            party_state=(getattr(inv, "filing_place_of_supply", None) or inv.customer.state or ""),
            party_gstin=(getattr(inv, "filing_party_gstin", None) or inv.customer.gstin or ""),
            tax_enabled=_tax_enabled(inv.invoice_type),
        )
        max_cn = _sales_note_headroom(inv, exclude_cn_id=note.pk)
        if note.grand_total > max_cn:
            raise BusinessRuleError(
                f"Credit note {note.grand_total} exceeds remaining invoiced value {max_cn}."
            )
        # CN-04: freight / handling can only be credited up to what the invoice charged.
        note_charges = Decimal(str(note.additional_charges or 0))
        if note_charges > 0:
            prior_charges = (
                SalesCreditNote.objects.filter(
                    sales_invoice=inv, status=SalesCreditNote.Status.COMPLETED
                )
                .exclude(pk=note.pk)
                .aggregate(total=Sum("additional_charges"))["total"]
                or Decimal("0")
            )
            billed_charges = Decimal(str(inv.additional_charges or 0))
            if prior_charges + note_charges > billed_charges + Decimal("0.01"):
                raise BusinessRuleError(
                    f"Additional charges credited ({prior_charges + note_charges}) exceed the charges "
                    f"billed on the invoice ({billed_charges})."
                )
        # CR-017: fully allocated invoices need confirm (allocations stay until refund/unallocate).
        allocated = (
            inv.allocations.filter(reversed_at__isnull=True).aggregate(s=Sum("amount"))["s"]
            or Decimal("0")
        )
        if allocated > 0 and not confirm_paid_invoice:
            from ledgers.services import LedgerService

            outstanding = LedgerService.sales_invoice_outstanding(inv)
            # After this CN, outstanding would go further negative / stay floored while alloc remains.
            if outstanding <= note.grand_total or allocated >= Decimal(str(inv.grand_total or 0)):
                raise_confirm_required(
                    [HelpCode.CONFIRM_CN_ON_PAID_INVOICE],
                    "This invoice has payment allocations. Completing the credit note leaves "
                    "over-allocation until you unallocate or refund. Pass confirm_paid_invoice=true "
                    "to proceed.",
                )
        # CR-124: when confirm_paid_invoice, unallocate only the overlap between
        # this note and money already allocated. A note for the unpaid remainder
        # leaves the receipt allocation in place. Only touch genuine
        # customer-receipt allocations — a mis-linked supplier_payment row on a
        # sales invoice must be left alone — and always re-apply the kept
        # remainder of a partially-consumed one.
        if allocated > 0 and confirm_paid_invoice:
            from ledgers.services import LedgerService
            from payments.services import PaymentService

            open_now = LedgerService.sales_invoice_outstanding(inv)
            remaining = Decimal(str(note.grand_total or 0)) - open_now
            if remaining < 0:
                remaining = Decimal("0")
            peeled = []
            for alloc in list(
                inv.allocations.select_for_update()
                .filter(reversed_at__isnull=True, receipt__isnull=False)
                .order_by("-id")
            ):
                if remaining <= 0:
                    break
                alloc_amt = Decimal(str(alloc.amount or 0))
                if alloc_amt <= 0:
                    continue
                receipt = alloc.receipt
                PaymentService.reverse_allocation(allocation=alloc, user=user)
                if alloc_amt <= remaining:
                    if receipt is not None:
                        peeled.append({"receipt_id": receipt.pk, "amount": str(alloc_amt)})
                    remaining -= alloc_amt
                else:
                    keep = alloc_amt - remaining
                    if receipt is not None:
                        peeled.append({"receipt_id": receipt.pk, "amount": str(remaining)})
                    remaining = Decimal("0")
                    if keep > 0 and receipt is not None:
                        PaymentService.allocate_receipt(
                            receipt=receipt, sales_invoice=inv, amount=keep, user=user
                        )
            if peeled:
                note.peeled_receipt_allocations = peeled
        # CR-026: unit_price override vs source line needs confirm.
        if not confirm_price_override:
            for item in note.items.select_related("source_item"):
                src = item.source_item
                if src is None:
                    continue
                if Decimal(str(item.unit_price or 0)) != Decimal(str(src.unit_price or 0)):
                    raise_confirm_required(
                        [HelpCode.CONFIRM_CN_PRICE_OVERRIDE],
                        "Credit note unit_price differs from the source invoice line. "
                        "Pass confirm_price_override=true to recalculate tax at the overridden price.",
                    )
        invoice_has_items = inv.items.exists()
        for item in note.items.select_related("source_item"):
            src = item.source_item
            if src is None:
                if invoice_has_items:
                    raise BusinessRuleError(
                        "Credit note lines must reference a source invoice item (source_item)."
                    )
                continue
            prior = prior_goods_credited_qty(src, exclude_note_id=note.pk)
            # DEP-02: a price-only credit leaves the goods; judge this line the same way.
            if not credit_line_uses_goods(
                note.reason, item.unit_price, item.discount_percent, src.unit_price, src.discount_percent
            ):
                continue
            if item.quantity + prior > src.quantity:
                raise BusinessRuleError(
                    f"Credit quantity {item.quantity} exceeds remaining qty "
                    f"{src.quantity - prior} on source line {src.pk}."
                )
        warnings = []
        tax_on = _tax_enabled(inv.invoice_type)
        if tax_on:
            _check_note_hsn(note, inv, "credit", warnings)
            # Sec 34(2): earlier of 30 Nov after the invoice's FY and the date the
            # annual return for that FY was filed (recorded on the GSTR-9 screen).
            if note.note_date and inv.invoice_date:
                from reporting.annual_filing import note_deadline

                deadline = note_deadline(note.company, inv.invoice_date)
                if note.note_date > deadline:
                    raise BusinessRuleError(
                        "Credit note date is past the Sec 34(2) deadline "
                        f"({deadline:%d %b %Y}: 30 Nov following the FY of the original invoice, "
                        "or the date its annual return was filed, whichever is earlier)."
                    )
        # BB-000736: period assert BEFORE next_number / status flip.
        if not note.filing_place_of_supply:
            note.filing_place_of_supply = inv.filing_place_of_supply or inv.customer.state or ""
        if not note.filing_party_gstin:
            note.filing_party_gstin = inv.filing_party_gstin or inv.customer.gstin or ""
        if note.company_gstin_id is None:
            note.company_gstin = inv.company_gstin

        if tax_on:
            from core.services.feature_flags import flag_enabled

            if flag_enabled(note.company, "ENABLE_GST_GUARD"):
                from reporting.gst_guard import (
                    apply_gst_guard_override,
                    document_has_gst_guard_override,
                    gst_guard_override_membership,
                    GST_GUARD_OVERRIDE_REASON_MAX,
                    GstGuardBlocked,
                    validate_document,
                )

                guard_result = validate_document(note)
                if (
                    guard_result.blocking
                    and not document_has_gst_guard_override(note)
                    and document_has_gst_guard_override(inv)
                ):
                    note.gst_guard_override_reason = inv.gst_guard_override_reason
                    note.gst_guard_overridden_by_id = inv.gst_guard_overridden_by_id
                    note.gst_guard_overridden_at = inv.gst_guard_overridden_at
                    note.save(update_fields=[
                        "gst_guard_override_reason",
                        "gst_guard_overridden_by",
                        "gst_guard_overridden_at",
                        "updated_at",
                    ])
                if guard_result.blocking and not document_has_gst_guard_override(note):
                    reason = (
                        gst_guard_override_reason.strip()
                        if isinstance(gst_guard_override_reason, str)
                        else ""
                    )
                    valid_reason = bool(reason) and len(reason) <= GST_GUARD_OVERRIDE_REASON_MAX
                    membership = (
                        gst_guard_override_membership(note.company, user) if valid_reason else None
                    )
                    if valid_reason and membership is not None:
                        apply_gst_guard_override(
                            note, result=guard_result, reason=reason, acting_user=user,
                        )
                    else:
                        raise GstGuardBlocked(guard_result)
                if guard_result.warning:
                    note._gst_guard_warnings = [
                        {"code": i.code, "message": i.message} for i in guard_result.warning
                    ]
                    for issue in guard_result.warning:
                        warnings.append(f"GST Guard: {issue.message}")
        # BB-000729: series keyed by GSTIN + FY.
        note.number = note.number or DocumentNumberService.next_number(
            note.company,
            "SALES_CREDIT_NOTE",
            gstin=resolve_series_gstin(note.company, note.company_gstin),
            on_date=note.note_date,
        )
        note.status = SalesCreditNote.Status.COMPLETED
        note.completed_at = timezone.now()
        note.pdf_status = SalesInvoice.PdfStatus.QUEUED
        note.updated_by = user
        note.save()
        mark_period_dirty_if_snapshotted(note.company, note.note_date)
        if note.company.accounting_enabled:
            from accounting.services import PostingService

            PostingService.post_note(
                note, source_type="SALES_CREDIT_NOTE", direction="SALES_CREDIT", user=user
            )
        record_document_event(document=note, user=user, event="sales_credit_note.completed")
        from planwave.services import stamp_document_party

        stamp_document_party(note)
        emit("document.completed", document=note, user=user, event="sales_credit_note.completed")
        emit("sales_credit_note.completed", document=note, user=user)
        return note, warnings

    @staticmethod
    @transaction.atomic
    def cancel_credit_note(note: SalesCreditNote, user):
        note = SalesCreditNote.objects.select_for_update().get(pk=note.pk)
        if note.status != SalesCreditNote.Status.COMPLETED:
            raise BusinessRuleError("Only completed credit notes can be cancelled.")
        from .irn_guard import assert_no_live_irn

        assert_no_live_irn(note, kind="credit note")
        if note.sales_return_id:
            from .models import SalesReturn

            sr = SalesReturn.objects.filter(pk=note.sales_return_id).first()
            if sr is not None and sr.status == SalesReturn.Status.COMPLETED:
                raise BusinessRuleError(
                    "This credit note is linked to a completed sales return. "
                    "Cancel the sales return instead — that will cancel this note."
                )
        from reporting.gst_periods import assert_period_allows_money_amend, mark_period_dirty_if_snapshotted

        assert_period_allows_money_amend(note.company, note.note_date, allow_soft_closed=True)
        if note.company.accounting_enabled:
            from accounting.models import JournalEntry
            from accounting.services import PostingService
            entry = JournalEntry.objects.filter(company=note.company, source_type="SALES_CREDIT_NOTE",
                source_id=note.id, purpose="COMPLETE", status=JournalEntry.Status.POSTED).first()
            if entry:
                PostingService.reverse(entry, user, note.note_date)
        note.status = SalesCreditNote.Status.CANCELLED
        note.cancelled_at = timezone.now()
        note.updated_by = user
        note.save()
        mark_period_dirty_if_snapshotted(note.company, note.note_date)
        _restore_peeled_receipt_allocations(note, user)
        record_document_event(document=note, user=user, event="sales_credit_note.cancelled")
        return note

    # ---------- Debit notes ----------

    @staticmethod
    @transaction.atomic
    def set_debit_note_items(note: SalesDebitNote, items_data, user):
        if note.status != SalesDebitNote.Status.DRAFT:
            raise BusinessRuleError("Completed debit note cannot be edited.")
        items_data = _normalize_items(items_data, note.company)
        _validate_lines(items_data, note.company, check_active=False)
        note.items.all().delete()
        items = _build_items(SalesDebitNoteItem, "debit_note", note, items_data)
        for item, src in zip(items, items_data):
            src_item = src.get("source_item", src.get("source_item_id"))
            if src_item is not None:
                item.source_item_id = src_item.pk if hasattr(src_item, "pk") else src_item
        if note.sales_invoice_id:
            inv = SalesInvoice.objects.select_for_update().get(
                pk=note.sales_invoice_id, company_id=note.company_id
            )
        else:
            inv = note.sales_invoice
        get_tax_engine(note.company).compute_document_totals(
            note,
            items,
            tax_enabled=_tax_enabled(inv.invoice_type),
            intra_state=_invoice_intra_state(inv),
            invoice_discount=note.invoice_discount,
            invoice_discount_mode=note.invoice_discount_mode,
            auto_round_off=note.auto_round_off,
            additional_charges=Decimal(str(getattr(note, "additional_charges", 0) or 0)),
        )
        _apply_rcm_memo_if_linked(note, items)
        SalesDebitNoteItem.objects.bulk_create(items)
        note.updated_by = user
        note.save()
        return note

    @staticmethod
    @transaction.atomic
    def complete_debit_note(
        note: SalesDebitNote, user, *, confirm_additional_debit: bool = False, gst_guard_override_reason=None,
        confirm_excessive_debit: bool = False, excessive_debit_reason: str | None = None,
    ):
        note = SalesDebitNote.objects.select_for_update().get(pk=note.pk)
        if note.status != SalesDebitNote.Status.DRAFT:
            raise BusinessRuleError(f"Cannot complete debit note in status {note.status}.")
        if not note.items.exists():
            raise BusinessRuleError("Cannot complete a debit note without line items.")
        # CR-093: lock source invoice before qty/value headroom (same as CN / CR-014).
        inv = SalesInvoice.objects.select_for_update().get(
            pk=note.sales_invoice_id,
            company_id=note.company_id,
        )
        if inv.status not in (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED):
            raise BusinessRuleError("Debit notes require a completed source invoice.")
        if note.note_date and inv.invoice_date and note.note_date < inv.invoice_date:
            raise BusinessRuleError(
                "Debit note date cannot be before the original invoice date."
            )
        assert_place_of_supply_for_gst(
            company=note.company,
            party_state=(getattr(inv, "filing_place_of_supply", None) or inv.customer.state or ""),
            party_gstin=(getattr(inv, "filing_party_gstin", None) or inv.customer.gstin or ""),
            tax_enabled=_tax_enabled(inv.invoice_type),
        )
        # BB-000303: cumulative DN headroom (CN creates room; prior DNs consume it).
        prior_dns = (
            SalesDebitNote.objects.filter(
                sales_invoice=inv, status=SalesDebitNote.Status.COMPLETED
            )
            .exclude(pk=note.pk)
            .aggregate(total=Sum("grand_total"))["total"]
            or Decimal("0")
        )
        prior_cns = (
            SalesCreditNote.objects.filter(
                sales_invoice=inv, status=SalesCreditNote.Status.COMPLETED
            ).aggregate(total=Sum("grand_total"))["total"]
            or Decimal("0")
        )
        # DNs may reverse CNs. Extra debit (price increase) needs confirm_additional_debit.
        cn_headroom = prior_cns - prior_dns
        extra = note.grand_total - max(cn_headroom, Decimal("0"))
        inv_value = Decimal(str(inv.grand_total or 0))
        # The cap is on everything billed above the original invoice, not per note:
        # earlier debit notes that already went past the credit notes count too, or
        # the cap could be sidestepped by splitting one big debit into several.
        extra = extra + max(prior_dns - prior_cns, Decimal("0"))
        if extra > inv_value:
            # DN-07: an Owner may knowingly bill past 100% of the invoice (major
            # price escalation) with a written reason, capped at 3x the invoice.
            if not confirm_excessive_debit:
                raise BusinessRuleError(
                    f"Additional debit {extra} exceeds original invoice value {inv.grand_total}. "
                    "An Owner can override this with a written reason."
                )
            from accounts.models import CompanyUser

            is_owner = CompanyUser.objects.filter(
                user=user, company=note.company, role=CompanyUser.Role.OWNER, is_active=True,
            ).exists()
            if not is_owner:
                raise BusinessRuleError("Only an Owner can override the invoice-value cap on a debit note.")
            reason = (excessive_debit_reason or "").strip()
            if not reason:
                raise BusinessRuleError("A written reason is required to bill above the invoice value.")
            if extra > inv_value * EXCESS_DEBIT_MAX_MULTIPLE:
                raise BusinessRuleError(
                    f"Additional debit {extra} exceeds {EXCESS_DEBIT_MAX_MULTIPLE}x the original invoice value."
                )
            from core.services.audit import AuditService

            AuditService.log(
                action="debit_note_excess_override",
                company=note.company,
                user=user,
                entity_type="SalesDebitNote",
                entity_id=note.pk,
                metadata={"extra": str(extra), "invoice_total": str(inv_value), "reason": reason[:255]},
            )
        if extra > 0 and not confirm_additional_debit:
            raise_confirm_required(
                [HelpCode.CONFIRM_ADDITIONAL_DEBIT],
                f"Debit note {note.grand_total} exceeds credit-note headroom {max(cn_headroom, Decimal('0'))}. "
                "Pass confirm_additional_debit=true to bill an additional amount on the original invoice.",
            )
        # CR-018: per-line qty cap vs source invoice lines (same as CN).
        invoice_has_items = inv.items.exists()
        for item in note.items.select_related("source_item"):
            src = item.source_item
            if src is None:
                if invoice_has_items:
                    raise BusinessRuleError(
                        "Debit note lines must reference a source invoice item (source_item)."
                    )
                continue
            prior = (
                SalesDebitNoteItem.objects.filter(
                    debit_note__sales_invoice=inv,
                    debit_note__status=SalesDebitNote.Status.COMPLETED,
                    source_item=src,
                )
                .exclude(debit_note_id=note.pk)
                .aggregate(s=Sum("quantity"))["s"]
                or Decimal("0")
            )
            if item.quantity + prior > src.quantity:
                raise BusinessRuleError(
                    f"Debit quantity {item.quantity} exceeds remaining qty "
                    f"{src.quantity - prior} on source line {src.pk}."
                )
        warnings = []
        if _tax_enabled(inv.invoice_type):
            _check_note_hsn(note, inv, "debit", warnings)
            from core.services.feature_flags import flag_enabled

            if flag_enabled(note.company, "ENABLE_GST_GUARD"):
                from reporting.gst_guard import (
                    GST_GUARD_OVERRIDE_REASON_MAX,
                    GstGuardBlocked,
                    apply_gst_guard_override,
                    document_has_gst_guard_override,
                    gst_guard_override_membership,
                    validate_document,
                )

                guard_result = validate_document(note)
                if (
                    guard_result.blocking
                    and not document_has_gst_guard_override(note)
                    and document_has_gst_guard_override(inv)
                ):
                    note.gst_guard_override_reason = inv.gst_guard_override_reason
                    note.gst_guard_overridden_by_id = inv.gst_guard_overridden_by_id
                    note.gst_guard_overridden_at = inv.gst_guard_overridden_at
                    note.save(update_fields=[
                        "gst_guard_override_reason",
                        "gst_guard_overridden_by",
                        "gst_guard_overridden_at",
                        "updated_at",
                    ])
                if guard_result.blocking and not document_has_gst_guard_override(note):
                    reason = (
                        gst_guard_override_reason.strip()
                        if isinstance(gst_guard_override_reason, str)
                        else ""
                    )
                    valid_reason = bool(reason) and len(reason) <= GST_GUARD_OVERRIDE_REASON_MAX
                    membership = (
                        gst_guard_override_membership(note.company, user) if valid_reason else None
                    )
                    if valid_reason and membership is not None:
                        apply_gst_guard_override(
                            note, result=guard_result, reason=reason, acting_user=user,
                        )
                    else:
                        raise GstGuardBlocked(guard_result)
                if guard_result.warning:
                    note._gst_guard_warnings = [
                        {"code": i.code, "message": i.message} for i in guard_result.warning
                    ]
                    for issue in guard_result.warning:
                        warnings.append(f"GST Guard: {issue.message}")
        # BB-000736: period assert BEFORE next_number / status flip.
        from reporting.gst_periods import assert_period_allows_money_amend, mark_period_dirty_if_snapshotted

        assert_period_allows_money_amend(note.company, note.note_date)
        if not note.filing_place_of_supply:
            note.filing_place_of_supply = inv.filing_place_of_supply or inv.customer.state or ""
        if not note.filing_party_gstin:
            note.filing_party_gstin = inv.filing_party_gstin or inv.customer.gstin or ""
        if note.company_gstin_id is None:
            note.company_gstin = inv.company_gstin
        note.number = note.number or DocumentNumberService.next_number(
            note.company,
            "SALES_DEBIT_NOTE",
            gstin=resolve_series_gstin(note.company, note.company_gstin),
            on_date=note.note_date,
        )
        note.status = SalesDebitNote.Status.COMPLETED
        note.completed_at = timezone.now()
        note.pdf_status = SalesInvoice.PdfStatus.QUEUED
        note.updated_by = user
        note.save()
        mark_period_dirty_if_snapshotted(note.company, note.note_date)
        if note.company.accounting_enabled:
            from accounting.services import PostingService

            PostingService.post_note(
                note, source_type="SALES_DEBIT_NOTE", direction="SALES_DEBIT", user=user
            )
        record_document_event(document=note, user=user, event="sales_debit_note.completed")
        from planwave.services import stamp_document_party

        stamp_document_party(note)
        emit("document.completed", document=note, user=user, event="sales_debit_note.completed")
        emit("sales_debit_note.completed", document=note, user=user)
        return note, warnings

    @staticmethod
    @transaction.atomic
    def cancel_debit_note(note: SalesDebitNote, user):
        note = SalesDebitNote.objects.select_for_update().get(pk=note.pk)
        if note.status != SalesDebitNote.Status.COMPLETED:
            raise BusinessRuleError("Only completed debit notes can be cancelled.")
        from .irn_guard import assert_no_live_irn

        assert_no_live_irn(note, kind="debit note")
        from reporting.gst_periods import assert_period_allows_money_amend, mark_period_dirty_if_snapshotted

        assert_period_allows_money_amend(note.company, note.note_date, allow_soft_closed=True)
        if note.company.accounting_enabled:
            from accounting.models import JournalEntry
            from accounting.services import PostingService
            entry = JournalEntry.objects.filter(company=note.company, source_type="SALES_DEBIT_NOTE",
                source_id=note.id, purpose="COMPLETE", status=JournalEntry.Status.POSTED).first()
            if entry:
                PostingService.reverse(entry, user, note.note_date)
        note.status = SalesDebitNote.Status.CANCELLED
        note.cancelled_at = timezone.now()
        note.updated_by = user
        note.save()
        mark_period_dirty_if_snapshotted(note.company, note.note_date)
        record_document_event(document=note, user=user, event="sales_debit_note.cancelled")
        return note

    # ---------- Sales orders ----------

    @staticmethod
    @transaction.atomic
    def set_order_items(order: SalesOrder, items_data, user, *, lines_are_exclusive: bool = False):
        """Replace the order's lines and recompute its totals.

        An order priced tax-inclusive stores the exclusive price it extracted from the inclusive
        one. When a draft is edited, the lines come back from the editor as stored (exclusive), so
        the caller passes ``lines_are_exclusive=True`` and they are not extracted a second time
        (editing a 118 inclusive order to quantity 2 used to give 200 instead of 236).
        """
        if order.status != SalesOrder.Status.DRAFT:
            raise BusinessRuleError("Converted, confirmed, or cancelled orders cannot be edited.")
        if getattr(order, "converted_invoice_id", None):
            raise BusinessRuleError("Orders converted to an invoice cannot be edited.")
        if order.challans.exclude(status=DeliveryChallan.Status.CANCELLED).exists():
            raise BusinessRuleError("Orders with active delivery challans cannot be edited.")
        items_data = _normalize_items(items_data, order.company)
        _validate_lines(items_data, order.company, check_active=True)
        order.items.all().delete()
        items = _build_items(SalesOrderItem, "sales_order", order, items_data)
        saved_price_mode = order.price_mode
        if lines_are_exclusive:
            order.price_mode = SalesInvoice.PriceMode.EXCLUSIVE
        get_tax_engine(order.company).compute_document_totals(
            order,
            items,
            tax_enabled=_tax_enabled(order.invoice_type),
            intra_state=party_intra_state(
                order.company,
                order.customer.state,
                order.customer.gstin or "",
                seller_state=(getattr(order.company_gstin, "state", None) or ""),
                seller_gstin=(getattr(order.company_gstin, "gstin", None) or ""),
                supply_type=getattr(order, "supply_type", ""),
            ),
            invoice_discount=order.invoice_discount,
            invoice_discount_mode=order.invoice_discount_mode,
            auto_round_off=order.auto_round_off,
            additional_charges=order.additional_charges,
        )
        order.price_mode = saved_price_mode
        SalesOrderItem.objects.bulk_create(items)
        # Lines in input order, for callers that map source lines to these rows.
        order._written_lines = items
        order.updated_by = user
        order.save()
        return order

    @staticmethod
    @transaction.atomic
    def confirm_sales_order(order: SalesOrder, user, override_reason=None):
        """DRAFT → CONFIRMED; reserve each line at the company default warehouse."""
        from inventory.services import InventoryService

        order = SalesOrder.objects.select_for_update().get(pk=order.pk)
        if order.status == SalesOrder.Status.CONFIRMED:
            raise BusinessRuleError("This order is already confirmed.", code="order_already_confirmed")
        if order.status != SalesOrder.Status.DRAFT:
            raise BusinessRuleError(f"Cannot confirm an order in status {order.status}.")
        if order.customer_id and order.customer.status != Customer.Status.ACTIVE:
            raise BusinessRuleError(
                f"Cannot confirm an order for {order.customer.billing_block_phrase}.",
                code="customer_not_active",
            )
        from planwave.services import assert_chronic_credit_allowed

        assert_chronic_credit_allowed(order)
        items = list(order.items.select_related("product"))
        if not items:
            raise BusinessRuleError("Cannot confirm an order without line items.")
        from sales.order_gates import apply_order_gates

        apply_order_gates(order, items, override_reason=override_reason, acting_user=user)
        warehouse = order.warehouse or InventoryService.default_warehouse(order.company)
        if order.warehouse_id is None:
            order.warehouse = warehouse
        for item in items:
            InventoryService.reserve_stock(
                order.company, warehouse, item.product, item.quantity, user
            )
        order.number = order.number or DocumentNumberService.next_number(
            order.company,
            "SALES_ORDER",
            gstin=resolve_series_gstin(order.company),
            on_date=order.order_date,
        )
        order.status = SalesOrder.Status.CONFIRMED
        order.stock_held = True
        order.updated_by = user
        order.save()
        return order

    @staticmethod
    def _require_confirmation_when_gates_on(order: SalesOrder):
        """Order gates run at confirmation. A draft must not skip them via convert."""
        from core.services.feature_flags import flag_enabled

        if flag_enabled(order.company, "ENABLE_ORDER_GATES") and order.status == SalesOrder.Status.DRAFT:
            raise BusinessRuleError(
                "Confirm this sales order before converting it.",
                code="confirm_required",
            )

    @staticmethod
    @transaction.atomic
    def convert_sales_order(order: SalesOrder, user, line_quantities=None):
        from inventory.services import InventoryService

        order = SalesOrder.objects.select_for_update().get(pk=order.pk, company_id=order.company_id)
        if order.status not in (
            SalesOrder.Status.DRAFT,
            SalesOrder.Status.CONFIRMED,
            SalesOrder.Status.PARTIALLY_CONVERTED,
        ):
            raise BusinessRuleError(f"Cannot convert an order in status {order.status}.")
        SalesNotesService._require_confirmation_when_gates_on(order)
        from .order_quantities import line_remaining, sync_order_counters

        # The counters are a cache of the documents: refresh before reading what is still open.
        sync_order_counters(order)
        order_lines = list(order.items.select_related("product"))
        requested = SalesNotesService._conversion_quantities(
            order_lines, line_quantities, counter="invoiced_quantity", order=order,
        )
        if order.customer.status != Customer.Status.ACTIVE:
            raise BusinessRuleError(f"Cannot create an invoice for {order.customer.billing_block_phrase}.")
        if not order.number:
            order.number = DocumentNumberService.next_number(
                order.company,
                "SALES_ORDER",
                gstin=resolve_series_gstin(order.company),
                on_date=order.order_date,
            )
        # CR-020: keep SO reservation until the invoice Completes (mirrors challan path).
        # Do not release here — release in SalesService.complete when converting SALE.
        invoice = SalesInvoice.objects.create(
            company=order.company,
            customer=order.customer,
            warehouse=order.warehouse or InventoryService.default_warehouse(order.company),
            invoice_type=order.invoice_type,
            company_gstin=getattr(order, "company_gstin", None) or _single_active_company_gstin(order.company),
            supply_type=getattr(order, "supply_type", None) or SalesInvoice.SupplyType.B2B,
            payment_terms_days=order.payment_terms_days,
            additional_charges=order.additional_charges,
            charges_hsn=getattr(order, "charges_hsn", "") or "",
            charges_gst_rate=getattr(order, "charges_gst_rate", 0) or 0,
            invoice_discount=order.invoice_discount,
            invoice_discount_mode=order.invoice_discount_mode,
            auto_round_off=order.auto_round_off,
            # An order priced tax-inclusive stores the exclusive price it extracted from the
            # inclusive one, so the invoice reads those lines as exclusive and totals match the
            # order. (Carrying INCLUSIVE over would extract tax from that price a second time.)
            price_mode=SalesInvoice.PriceMode.EXCLUSIVE,
            notes=order.notes,
            terms_text=order.terms_text,
            created_by=user,
            updated_by=user,
        )
        items_data = []
        for item in order_lines:
            qty = requested[item.pk]
            if qty <= 0:
                continue
            items_data.append({
                "product": item.product,
                "description": item.description,
                "quantity": qty,
                "unit_price": item.unit_price,
                "discount_percent": item.discount_percent,
                "gst_rate": item.gst_rate,
                "cess_rate": getattr(item, "cess_rate", Decimal("0")),
                "cess_amount": getattr(item, "cess_amount", Decimal("0")),
                "supply_nature": getattr(item, "supply_nature", None),
                "hsn_code": getattr(item, "hsn_code", "") or "",
                "rate_override": True,
                "rate_override_reason": (
                    getattr(item, "rate_override_reason", "") or "Copied from sales order"
                ),
                # BB-000732: preserve lot/serial identity through conversion.
                "batch": getattr(item, "batch", None),
                "batch_no": getattr(item, "batch_no", "") or "",
                "serial_numbers": getattr(item, "serial_numbers", None) or [],
            })
        if not items_data:
            raise BusinessRuleError(SalesNotesService._nothing_left_message(order, "invoiced_quantity"))
        # Link first so the freeze check in set_items sees the sibling invoices of this order.
        invoice.source_order = order
        invoice.save(update_fields=["source_order"])
        SalesService.set_items(invoice, items_data, user)
        from sales.order_gates import copy_credit_override

        copy_credit_override(order, invoice)
        # Keep a confirmed order confirmed until the invoice Completes when the
        # whole quantity moved. A short convert stays open for the remainder.
        sync_order_counters(order)
        order_lines = list(order.items.all())
        remaining = any(line_remaining(item) > 0 for item in order_lines)
        order.converted_invoice = invoice
        order.updated_by = user
        update_fields = ["converted_invoice", "updated_by", "updated_at"]
        if remaining:
            order.status = SalesOrder.Status.PARTIALLY_CONVERTED
            update_fields.append("status")
        order.save(update_fields=update_fields)
        return invoice

    @staticmethod
    def release_order_conversion(order, items, *, counter="invoiced_quantity", unlink_invoice_id=None):
        """Give back the quantity a discarded draft invoice or challan had taken from its order.

        Converting counts the quantity on the order lines at once. Without this reversal,
        deleting the draft leaves those lines counted: the order cannot be converted again, and
        a partly converted order cannot be cancelled either.
        """
        if order is None:
            return
        order = SalesOrder.objects.select_for_update().get(pk=order.pk)
        taken: dict = {}
        for it in items:
            taken[it.product_id] = taken.get(it.product_id, Decimal("0")) + Decimal(str(it.quantity or 0))
        lines = list(order.items.all())
        for line in lines:
            give = min(taken.get(line.product_id, Decimal("0")), Decimal(str(getattr(line, counter) or 0)))
            if give > 0:
                setattr(line, counter, Decimal(str(getattr(line, counter) or 0)) - give)
                taken[line.product_id] -= give
                line.save(update_fields=[counter])
        fields = ["updated_at"]
        if unlink_invoice_id and order.converted_invoice_id == unlink_invoice_id:
            order.converted_invoice = None
            fields.append("converted_invoice")
        if order.status in (SalesOrder.Status.PARTIALLY_CONVERTED, SalesOrder.Status.CONVERTED):
            still = any(
                Decimal(str(row.invoiced_quantity or 0)) > 0 or Decimal(str(row.shipped_quantity or 0)) > 0
                for row in lines
            )
            if not still and order.status == SalesOrder.Status.PARTIALLY_CONVERTED:
                order.status = SalesOrder.Status.CONFIRMED if order.stock_held else SalesOrder.Status.DRAFT
                fields.append("status")
        order.save(update_fields=fields)

    @staticmethod
    def _conversion_quantities(order_lines, line_quantities, *, counter, order=None):
        """Map each line id to the quantity this convert should take.

        A challan and a direct invoice draw on the same remainder: a line's open quantity is what
        is neither on a live challan nor on a live direct invoice (H-12). Omitted lines take nothing
        when the caller passed an explicit map. A request above the remaining quantity is refused.
        """
        from .order_quantities import line_remaining

        explicit = line_quantities is not None
        lookup = {}
        if explicit:
            if isinstance(line_quantities, dict):
                pairs = line_quantities.items()
            else:
                pairs = (
                    (row.get("id", row.get("line_id")), row.get("quantity"))
                    for row in line_quantities
                )
            for key, raw in pairs:
                lookup[int(key)] = Decimal(str(raw))
        requested = {}
        any_qty = False
        for item in order_lines:
            remaining = line_remaining(item)
            if explicit:
                if item.pk not in lookup:
                    requested[item.pk] = Decimal("0")
                    continue
                qty = lookup[item.pk]
            else:
                qty = remaining
            if qty < 0:
                raise BusinessRuleError("Conversion quantity must be greater than zero.")
            if qty > remaining:
                from .order_quantities import fmt_qty

                raise BusinessRuleError(
                    f"Cannot convert {fmt_qty(qty)} of '{item.product.name}': "
                    f"only {fmt_qty(remaining)} is still open on this sales order."
                )
            if qty > 0:
                any_qty = True
            requested[item.pk] = qty
        if not any_qty:
            raise BusinessRuleError(SalesNotesService._nothing_left_message(order, counter))
        return requested

    @staticmethod
    def _nothing_left_message(order, counter) -> str:
        """Why no quantity can be taken, naming what already holds it."""
        from .order_quantities import invoices_for_order, live_challans_for_order

        if counter == "invoiced_quantity":
            if order is not None and live_challans_for_order(order).exists():
                return (
                    "This sales order already has a delivery challan for all of its quantity. "
                    "Convert that challan to an invoice instead."
                )
            return "This sales order already has an invoice."
        if order is not None and invoices_for_order(order).exists():
            return (
                "This sales order already has an invoice for all of its quantity. Cancel or delete "
                "that invoice before converting to a delivery challan."
            )
        return "This sales order already has a delivery challan."

    @staticmethod
    @transaction.atomic
    def convert_sales_order_to_challan(order: SalesOrder, user, line_quantities=None):
        from .models import DeliveryChallan
        from inventory.services import InventoryService

        order = SalesOrder.objects.select_for_update().get(pk=order.pk, company_id=order.company_id)
        if order.status not in (
            SalesOrder.Status.DRAFT,
            SalesOrder.Status.CONFIRMED,
            SalesOrder.Status.PARTIALLY_CONVERTED,
        ):
            raise BusinessRuleError(f"Cannot convert an order in status {order.status}.")
        SalesNotesService._require_confirmation_when_gates_on(order)
        if order.customer.status != Customer.Status.ACTIVE:
            raise BusinessRuleError(f"Cannot create a delivery challan for {order.customer.billing_block_phrase}.")
        if not order.number:
            order.number = DocumentNumberService.next_number(
                order.company,
                "SALES_ORDER",
                gstin=resolve_series_gstin(order.company),
                on_date=order.order_date,
            )
        # CR-120: the same units must not be shipped and invoiced directly (double stock and
        # receivable). A challan and a direct invoice draw on one remainder (H-12): taking the
        # last units on one leaves nothing for the other, and a partly shipped order can still be
        # invoiced for the rest.
        from .order_quantities import line_remaining, sync_order_counters

        # One open draft challan at a time: finish or cancel it before the next batch is cut.
        if DeliveryChallan.objects.filter(sales_order=order, status=DeliveryChallan.Status.DRAFT).exists():
            raise BusinessRuleError("This sales order already has a delivery challan.")
        sync_order_counters(order)
        order_lines = list(order.items.select_related("product"))
        requested = SalesNotesService._conversion_quantities(
            order_lines, line_quantities, counter="shipped_quantity", order=order,
        )
        # Keep SO CONFIRMED/DRAFT until the challan Completes so reservations stay
        # valid and cancel_sales_order still works on a draft challan.
        challan = DeliveryChallan.objects.create(
            company=order.company,
            customer=order.customer,
            warehouse=order.warehouse or InventoryService.default_warehouse(order.company),
            sales_order=order,
            challan_date=timezone.localdate(),
            notes=order.notes,
            created_by=user,
            updated_by=user,
            delivery_address=getattr(order, "delivery_address", "") or "",
        )
        items_data = []
        for item in order_lines:
            qty = requested[item.pk]
            if qty <= 0:
                continue
            items_data.append({
                "product": item.product,
                "description": item.description,
                "quantity": qty,
                "unit_price": item.unit_price,
                "discount_percent": item.discount_percent,
                "gst_rate": item.gst_rate,
                "cess_rate": getattr(item, "cess_rate", Decimal("0")),
                "cess_amount": getattr(item, "cess_amount", Decimal("0")),
                "supply_nature": getattr(item, "supply_nature", None),
                "hsn_code": getattr(item, "hsn_code", "") or "",
                "batch": getattr(item, "batch", None),
                "batch_no": getattr(item, "batch_no", "") or "",
                "serial_numbers": getattr(item, "serial_numbers", None) or [],
                "expected_price": getattr(item, "expected_price", None) or Decimal("0"),
            })
        if not items_data:
            raise BusinessRuleError(SalesNotesService._nothing_left_message(order, "shipped_quantity"))
        SalesNotesService.set_challan_items(challan, items_data, user)
        sync_order_counters(order)
        remaining = any(line_remaining(item) > 0 for item in order.items.all())
        order.updated_by = user
        update_fields = ["updated_by", "updated_at"]
        if remaining and order.status != SalesOrder.Status.DRAFT:
            order.status = SalesOrder.Status.PARTIALLY_CONVERTED
            update_fields.append("status")
        order.save(update_fields=update_fields)
        return challan

    @staticmethod
    def reopen_order_after_goods_back(order: SalesOrder, challan, quantities, user):
        """A completed challan was cancelled or its goods came back: the order owes them again.

        ``quantities`` maps product id to the quantity returning. Stock is reserved again for it
        (so the order can be shipped a second time without overselling), the line counters are
        rebuilt from the live documents, and the status follows what is still completed.
        """
        from inventory.services import InventoryService

        from .order_quantities import sync_order_counters

        order = SalesOrder.objects.select_for_update().get(pk=order.pk, company_id=order.company_id)
        if order.status == SalesOrder.Status.CANCELLED:
            sync_order_counters(order)
            return order
        warehouse = order.warehouse or InventoryService.default_warehouse(order.company)
        if order.stock_held:
            # Only an order that held stock gets it held again; a draft that never reserved
            # anything stays unreserved until someone confirms it.
            products = {line.product_id: line.product for line in order.items.select_related("product")}
            for product_id, qty in quantities.items():
                product = products.get(product_id)
                if product is not None and qty > 0:
                    InventoryService.reserve_stock(order.company, warehouse, product, qty, user)
        sync_order_counters(order)
        from .order_quantities import invoices_for_order, shipped_by_product

        # Net of returns: a challan whose goods all came back is not "shipped" any more.
        completed_challans = sum(shipped_by_product(order, completed_only=True).values(), Decimal("0")) > 0
        completed_invoices = invoices_for_order(order).filter(
            status__in=OPEN_RECEIVABLE_STATUSES
        ).exists()
        if completed_challans or completed_invoices:
            order.status = SalesOrder.Status.PARTIALLY_CONVERTED
        else:
            order.status = SalesOrder.Status.CONFIRMED if order.stock_held else SalesOrder.Status.DRAFT
        order.updated_by = user
        order.save(update_fields=["status", "updated_by", "updated_at"])
        return order

    @staticmethod
    @transaction.atomic
    def cancel_sales_order(order: SalesOrder, user):
        from inventory.services import InventoryService

        from .order_quantities import invoices_for_order, live_challans_for_order, order_still_held

        order = SalesOrder.objects.select_for_update().get(pk=order.pk, company_id=order.company_id)
        if order.status not in (SalesOrder.Status.DRAFT, SalesOrder.Status.CONFIRMED):
            raise BusinessRuleError(f"Cannot cancel an order in status {order.status}.")
        live_invoices = list(invoices_for_order(order).order_by("id"))
        if live_invoices:
            names = ", ".join(inv.number or f"draft #{inv.pk}" for inv in live_invoices[:5])
            raise BusinessRuleError(
                f"Cancel or delete the invoice(s) made from this order first ({names})."
            )
        if live_challans_for_order(order).exists():
            raise BusinessRuleError(
                "Cancel or reverse outstanding delivery challans before cancelling this order."
            )
        if order.stock_held:
            warehouse = order.warehouse or InventoryService.default_warehouse(order.company)
            held = order_still_held(order)
            for item in order.items.select_related("product"):
                qty = held.get(item.product_id, Decimal("0"))
                if qty > 0:
                    InventoryService.release_reservation(order.company, warehouse, item.product, qty, user)
                    held[item.product_id] = Decimal("0")
            order.stock_held = False
        order.status = SalesOrder.Status.CANCELLED
        order.updated_by = user
        order.save()
        from .models import QuotationConversion
        from .quotation_conversions import QuotationConversionService

        QuotationConversionService.release_for_order(
            order, user, QuotationConversion.ReleaseReason.ORDER_CANCELLED
        )
        return order

    # ---------- Delivery challan ----------

    @staticmethod
    @transaction.atomic
    def set_challan_items(challan: DeliveryChallan, items_data, user):
        if challan.status != DeliveryChallan.Status.DRAFT:
            raise BusinessRuleError("Completed challan cannot be edited.")
        items_data = _normalize_items(items_data, challan.company)
        _validate_lines(items_data, challan.company, check_active=True)
        order = challan.sales_order if challan.sales_order_id else None
        if order is not None:
            SalesNotesService._assert_challan_within_order(challan, order, items_data)
        challan.items.all().delete()
        items = _build_items(DeliveryChallanItem, "challan", challan, items_data)
        from accounts.models import Company, CompanyGstin

        stamp = getattr(challan, "company_gstin", None)
        gstin = (getattr(stamp, "gstin", None) or "").strip() if stamp is not None else ""
        if not gstin:
            gstin = (getattr(challan.company, "gstin", None) or "").strip()
        if not gstin:
            active = (
                CompanyGstin.objects.filter(company=challan.company, is_active=True)
                .exclude(gstin="")
                .order_by("-is_primary", "id")
                .first()
            )
            gstin = (getattr(active, "gstin", None) or "").strip() if active else ""
        reg = getattr(challan.company, "registration_type", None)
        tax_enabled = bool(gstin) and reg == Company.RegistrationType.REGULAR
        # A challan made from a Bill of Supply order carries no tax (H-11).
        if order is not None and order.invoice_type == SalesInvoice.InvoiceType.NON_GST:
            tax_enabled = False
        get_tax_engine(challan.company).compute_document_totals(
            challan,
            items,
            tax_enabled=tax_enabled,
            intra_state=party_intra_state(
                challan.company,
                getattr(challan.customer, "state", None) or "",
                getattr(challan.customer, "gstin", None) or "",
            ),
            auto_round_off=True,
            additional_charges=Decimal("0"),
        )
        DeliveryChallanItem.objects.bulk_create(items)
        challan.updated_by = user
        challan.save()
        if order is not None:
            from .order_quantities import sync_order_counters

            sync_order_counters(order)
        return challan

    @staticmethod
    def _assert_challan_within_order(challan, order, items_data) -> None:
        """A challan linked to an order may carry only what the order still owes (H-08).

        The "To challan" button already respects this; a challan built by hand and linked to the
        order did not, and its quantities never reached the order's counters. The challan's own
        current lines are not counted against it, so editing a draft is not refused by itself.
        """
        from .order_quantities import remaining_excluding_challan

        wanted: dict[int, Decimal] = {}
        names: dict[int, str] = {}
        for line in items_data:
            product = line["product"]
            wanted[product.pk] = wanted.get(product.pk, Decimal("0")) + Decimal(str(line["quantity"]))
            names[product.pk] = product.name
        allowed = remaining_excluding_challan(order, challan)
        for product_id, qty in wanted.items():
            left = allowed.get(product_id)
            if left is None:
                raise BusinessRuleError(
                    f"'{names[product_id]}' is not on sales order {order.number or order.pk}, "
                    "so it cannot be shipped against it."
                )
            if qty > left:
                from .order_quantities import fmt_qty

                raise BusinessRuleError(
                    f"Cannot ship {fmt_qty(qty)} of '{names[product_id]}': only {fmt_qty(left)} is still open on "
                    f"sales order {order.number or order.pk}."
                )

    @staticmethod
    @transaction.atomic
    def complete_challan(challan: DeliveryChallan, user):
        from inventory.models import MovementType
        from inventory.services import InventoryService, InventoryValuationService

        challan = DeliveryChallan.objects.select_for_update().get(pk=challan.pk)
        if challan.status != DeliveryChallan.Status.DRAFT:
            raise BusinessRuleError(f"Cannot complete challan in status {challan.status}.")
        if challan.customer_id and challan.customer.status != Customer.Status.ACTIVE:
            raise BusinessRuleError(
                f"Cannot complete a delivery challan for {challan.customer.billing_block_phrase}.",
                code="customer_not_active",
            )
        items = list(challan.items.select_related("product"))
        if not items:
            raise BusinessRuleError("Cannot complete a challan without line items.")
        # CR-019: gate closed periods before stock/number when challan posts stock.
        if challan.company.stock_on_delivery_challan:
            from reporting.gst_periods import assert_period_allows_money_amend

            assert_period_allows_money_amend(challan.company, challan.challan_date)
        # BB-000729: series keyed by GSTIN + FY (primary GSTIN when challan has no stamp).
        challan.number = challan.number or DocumentNumberService.next_number(
            challan.company,
            "DELIVERY_CHALLAN",
            gstin=resolve_series_gstin(challan.company),
            on_date=challan.challan_date,
        )
        # Release SO reservations before SALE so available qty matches on-hand.
        order = None
        if challan.sales_order_id:
            from .models import SalesOrder
            from .order_quantities import order_still_held

            # CR-094: never mutate another tenant's SO / reservations.
            order = SalesOrder.objects.select_for_update().get(
                pk=challan.sales_order_id,
                company_id=challan.company_id,
            )
            if order.status == SalesOrder.Status.CANCELLED:
                raise BusinessRuleError("Cannot complete a challan for a cancelled sales order.")
            warehouse = order.warehouse or InventoryService.default_warehouse(challan.company)
            # Give back what this challan ships, and never more than the order still holds: an
            # unconfirmed order holds nothing, and a second release would eat other orders' hold.
            held = order_still_held(order)
            challan_qty: dict[int, Decimal] = {}
            for item in items:
                challan_qty[item.product_id] = challan_qty.get(item.product_id, Decimal("0")) + Decimal(
                    str(item.quantity or 0)
                )
            for product in {item.product_id: item.product for item in items}.values():
                release_qty = min(held.get(product.pk, Decimal("0")), challan_qty.get(product.pk, Decimal("0")))
                if release_qty > 0:
                    InventoryService.release_reservation(challan.company, warehouse, product, release_qty, user)
        stock_posted = False
        if challan.company.stock_on_delivery_challan:
            from inventory.services import SerialNumberService
            from inventory.models import SerialNumber

            warehouse = challan.warehouse or InventoryService.default_warehouse(challan.company)
            if challan.warehouse_id is None:
                challan.warehouse = warehouse
            for item in items:
                if item.product.track_serial:
                    SerialNumberService.transition(
                        company=challan.company,
                        product=item.product,
                        warehouse=warehouse,
                        numbers=item.serial_numbers,
                        quantity=item.quantity,
                        source=SerialNumber.Status.AVAILABLE,
                        target=SerialNumber.Status.SOLD,
                        user=user,
                    )
                # BB-000343: FEFO/batch allocation same as invoice complete.
                _wh = warehouse
                class _ChallanProxy:
                    company = challan.company
                    warehouse = _wh

                proxy = _ChallanProxy()
                # Reuse SalesService batch resolver via a duck-typed line.
                for batch, quantity in SalesService._sale_batches(proxy, item):
                    unit_cost = InventoryValuationService.unit_cost(
                        challan.company, item.product, warehouse, batch=batch
                    )
                    InventoryService.post_movement(
                        company=challan.company,
                        warehouse=warehouse,
                        product=item.product,
                        batch=batch,
                        movement_type=MovementType.SALE,
                        quantity=quantity,
                        unit_cost=unit_cost,
                        reference_type="delivery_challan",
                        reference_id=challan.pk,
                        # Ties the movement to its challan line (like SALE_LINE on invoices).
                        reason=f"CHALLAN_LINE:{item.pk}" if item.pk else "",
                        user=user,
                    )
            stock_posted = True
        from planwave.services import assert_chronic_credit_allowed

        credit_delivery = True
        if challan.sales_order_id:
            linked_terms = int(getattr(getattr(challan, "sales_order", None), "payment_terms_days", 0) or 0)
            credit_delivery = linked_terms > 0
        if credit_delivery:
            assert_chronic_credit_allowed(challan, force=True)
        challan.status = DeliveryChallan.Status.COMPLETED
        challan.completed_at = timezone.now()
        challan.pdf_status = SalesInvoice.PdfStatus.QUEUED
        challan.stock_posted = stock_posted
        challan.updated_by = user
        challan.save()
        if order is not None:
            from .order_quantities import recompute_order_status

            recompute_order_status(order, user)
        record_document_event(document=challan, user=user, event="delivery_challan.completed")
        emit("document.completed", document=challan, user=user, event="delivery_challan.completed")
        emit("delivery_challan.completed", document=challan, user=user)
        return challan

    @staticmethod
    @transaction.atomic
    def convert_delivery_challan(challan: DeliveryChallan, user):
        """COMPLETED challan → draft sales invoice; links converted_invoice for stock skip."""
        challan = DeliveryChallan.objects.select_for_update().get(pk=challan.pk)
        if challan.status != DeliveryChallan.Status.COMPLETED:
            raise BusinessRuleError(f"Cannot convert a challan in status {challan.status}.")
        if challan.converted_invoice_id:
            raise BusinessRuleError("Challan has already been converted to an invoice.")
        if challan.customer.status != Customer.Status.ACTIVE:
            raise BusinessRuleError(f"Cannot create an invoice for {challan.customer.billing_block_phrase}.")
        order = challan.sales_order
        # BB-000342 / BB-000399: composition/unregistered → NON_GST (Bill of Supply), not GST.
        from accounts.models import Company, CompanyGstin
        from inventory.services import InventoryService

        gstin = (getattr(challan.company, "gstin", None) or "").strip()
        if not gstin:
            stamp = getattr(challan, "company_gstin", None)
            gstin = (getattr(stamp, "gstin", None) or "").strip()
        if not gstin:
            active = (
                CompanyGstin.objects.filter(company=challan.company, is_active=True)
                .exclude(gstin="")
                .order_by("-is_primary", "id")
                .first()
            )
            gstin = (getattr(active, "gstin", None) or "").strip() if active else ""
        reg = challan.company.registration_type
        if reg == Company.RegistrationType.REGULAR and gstin:
            invoice_type = SalesInvoice.InvoiceType.GST
        else:
            invoice_type = SalesInvoice.InvoiceType.NON_GST
        # A challan made from a Bill of Supply order stays a Bill of Supply (H-11). The registration
        # rule above can only downgrade GST to non-GST, never turn a non-GST order into a tax invoice.
        if order is not None and order.invoice_type == SalesInvoice.InvoiceType.NON_GST:
            invoice_type = SalesInvoice.InvoiceType.NON_GST
        order = challan.sales_order
        invoice = SalesInvoice.objects.create(
            company=challan.company,
            customer=challan.customer,
            warehouse=challan.warehouse or InventoryService.default_warehouse(challan.company),
            invoice_type=invoice_type,
            company_gstin=getattr(challan, "company_gstin", None)
            or _single_active_company_gstin(challan.company),
            supply_type=getattr(order, "supply_type", None) or SalesInvoice.SupplyType.B2B,
            payment_terms_days=getattr(order, "payment_terms_days", 0) if order else 0,
            additional_charges=getattr(order, "additional_charges", 0) if order else Decimal("0"),
            invoice_discount=getattr(order, "invoice_discount", 0) if order else Decimal("0"),
            invoice_discount_mode=(
                getattr(order, "invoice_discount_mode", None)
                or SalesInvoice.DiscountMode.AFTER_TAX
            ),
            auto_round_off=getattr(order, "auto_round_off", True) if order else True,
            # Challan and order lines hold exclusive unit prices (an inclusive order's price was
            # extracted when it was saved). Copying INCLUSIVE here made the invoice take tax out of
            # the price a second time: a 118 inclusive order became a 100 invoice (H-10).
            price_mode=SalesInvoice.PriceMode.EXCLUSIVE,
            terms_text=getattr(order, "terms_text", "") if order else "",
            notes=challan.notes or (getattr(order, "notes", "") if order else ""),
            vehicle_number=challan.vehicle_number,
            transporter_name=challan.transporter_name,
            transporter_id=challan.transporter_id,
            transport_distance_km=challan.transport_distance_km,
            created_by=user,
            updated_by=user,
        )
        # Goods that came back against the challan are not billed: the invoice carries what stayed.
        from .challan_return import ChallanReturnService

        returned_left = {
            pid: Decimal(str(q or 0)) for pid, q in ChallanReturnService.returned_quantities(challan).items()
        }
        net_quantity: dict[int, Decimal] = {}
        for item in challan.items.all():
            q = Decimal(str(item.quantity or 0))
            back = min(q, returned_left.get(item.product_id, Decimal("0")))
            returned_left[item.product_id] = returned_left.get(item.product_id, Decimal("0")) - back
            net_quantity[item.pk] = q - back
        if net_quantity and all(q <= 0 for q in net_quantity.values()):
            raise BusinessRuleError("Every item on this challan came back, so there is nothing to invoice.")
        if any(
            q < Decimal(str(item.quantity or 0)) and item.product.track_serial
            for item in challan.items.select_related("product")
            for q in [net_quantity[item.pk]]
        ):
            raise BusinessRuleError(
                "Serial-numbered goods came back against this challan. Record the return first, then bill "
                "the remaining goods through a new challan or invoice."
            )
        items_data = [
            {
                "product": item.product,
                "description": item.description,
                "quantity": net_quantity[item.pk],
                "unit_price": item.unit_price,
                "discount_percent": item.discount_percent,
                "gst_rate": item.gst_rate,
                # Keep the challan-stamped GST rate; HSN catalog must not re-rate
                # at convert (persona + mixed-suite HSN seed otherwise diverge).
                "rate_override": True,
                "rate_override_reason": (
                    getattr(item, "rate_override_reason", "") or "Copied from delivery challan"
                ),
                "cess_rate": getattr(item, "cess_rate", Decimal("0")),
                "cess_amount": getattr(item, "cess_amount", Decimal("0")),
                "supply_nature": getattr(item, "supply_nature", None),
                "hsn_code": getattr(item, "hsn_code", "") or "",
                "unit_price_inclusive": getattr(item, "unit_price_inclusive", None),
                # BB-000732: preserve lot/serial identity through conversion.
                "batch": getattr(item, "batch", None),
                "batch_no": getattr(item, "batch_no", "") or "",
                "serial_numbers": getattr(item, "serial_numbers", None) or [],
            }
            for item in challan.items.select_related("product", "batch")
            if net_quantity[item.pk] > 0
        ]
        SalesService.set_items(invoice, items_data, user)
        from sales.order_gates import copy_credit_override

        copy_credit_override(order, invoice)
        challan.converted_invoice = invoice
        challan.updated_by = user
        challan.save(update_fields=["converted_invoice", "updated_by", "updated_at"])
        order = challan.sales_order
        # A partly shipped order has one invoice per challan. ``converted_invoice`` points at the
        # latest; the full set is read through ``invoices_for_order`` (H-13).
        if order is not None:
            order.converted_invoice = invoice
            order.updated_by = user
            order.save(update_fields=["converted_invoice", "updated_by", "updated_at"])
        return invoice

    @staticmethod
    @transaction.atomic
    def cancel_challan(challan: DeliveryChallan, user):
        from inventory.models import MovementType
        from inventory.services import InventoryService

        challan = DeliveryChallan.objects.select_for_update().get(pk=challan.pk)
        if challan.status == DeliveryChallan.Status.DRAFT:
            SalesNotesService.release_order_conversion(
                getattr(challan, "sales_order", None), challan.items.all(), counter="shipped_quantity",
            )
            challan.status = DeliveryChallan.Status.CANCELLED
            challan.cancelled_at = timezone.now()
            challan.updated_by = user
            challan.save()
            if challan.sales_order_id:
                from .order_quantities import recompute_order_status, sync_order_counters

                sync_order_counters(challan.sales_order)
                recompute_order_status(challan.sales_order, user)
            return challan
        if challan.status != DeliveryChallan.Status.COMPLETED:
            raise BusinessRuleError("Only draft or completed challans can be cancelled.")
        from .models import DeliveryChallanReturn

        if DeliveryChallanReturn.objects.filter(
            challan=challan, status=DeliveryChallanReturn.Status.COMPLETED
        ).exists():
            # Cancelling would put the returned goods back into stock a second time.
            raise BusinessRuleError(
                "Goods have already come back against this challan. It cannot be cancelled."
            )
        # G-22: mirrors complete_challan's own CR-019 gate — reversing the
        # same stock posting must be checked too, not just the forward posting.
        # allow_soft_closed=True matches the cancel/reverse convention used by
        # every other call site of this gate.
        if challan.stock_posted:
            from reporting.gst_periods import assert_period_allows_money_amend

            assert_period_allows_money_amend(
                challan.company, challan.challan_date, allow_soft_closed=True
            )
        from .irn_guard import assert_no_live_eway

        assert_no_live_eway(challan, kind="delivery challan")
        if challan.converted_invoice_id:
            inv = challan.converted_invoice
            if inv.status in (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED):
                raise BusinessRuleError(
                    "Cannot cancel a challan whose converted invoice is completed."
                )
        if challan.stock_posted:
            from inventory.models import SerialNumber, StockMovement
            from inventory.services import SerialNumberService

            warehouse = challan.warehouse or InventoryService.default_warehouse(challan.company)
            # BB-000343 / BB-000717: restore per SALE movement lot + peels; serials SOLD→AVAILABLE.
            for move in StockMovement.objects.filter(
                company=challan.company,
                movement_type=MovementType.SALE,
                reference_type="delivery_challan",
                reference_id=str(challan.pk),
            ):
                inbound = InventoryService.post_movement(
                    company=challan.company,
                    warehouse=move.warehouse,
                    product=move.product,
                    batch=move.batch,
                    movement_type=MovementType.ADJUSTMENT,
                    quantity=abs(Decimal(str(move.quantity))),
                    unit_cost=move.unit_cost,
                    reference_type="delivery_challan_cancel",
                    reference_id=challan.pk,
                    reason=f"Cancellation of {challan.number}",
                    user=user,
                )
                InventoryService.restore_fifo_peels(move, inbound)
            for item in challan.items.select_related("product"):
                if item.product.track_serial and item.serial_numbers:
                    SerialNumberService.transition(
                        company=challan.company,
                        product=item.product,
                        warehouse=warehouse,
                        numbers=item.serial_numbers,
                        quantity=item.quantity,
                        source=SerialNumber.Status.SOLD,
                        target=SerialNumber.Status.AVAILABLE,
                        user=user,
                    )
            challan.stock_posted = False
        challan.status = DeliveryChallan.Status.CANCELLED
        challan.cancelled_at = timezone.now()
        challan.updated_by = user
        challan.save()
        order = challan.sales_order
        if order is not None:
            # The goods are back: give the order its quantity back and hold stock for it again.
            quantities: dict[int, Decimal] = {}
            for item in challan.items.select_related("product"):
                quantities[item.product_id] = quantities.get(item.product_id, Decimal("0")) + Decimal(
                    str(item.quantity or 0)
                )
            SalesNotesService.reopen_order_after_goods_back(order, challan, quantities, user)
        record_document_event(document=challan, user=user, event="delivery_challan.cancelled")
        return challan
