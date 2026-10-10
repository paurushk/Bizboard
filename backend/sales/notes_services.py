"""Sales credit/debit notes, orders, and delivery challans (Phase 1 / 1.5)."""

from datetime import date
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


def _restore_peeled_receipt_allocations(note, user):
    """Put receipt slices back on the source invoice after a credit note is cancelled."""
    slices = list(note.peeled_receipt_allocations or [])
    if not slices or not note.sales_invoice_id:
        return
    from ledgers.services import LedgerService
    from payments.models import CustomerReceipt, ReceiptStatus
    from payments.services import PaymentService, _allocated_of_payment

    inv = SalesInvoice.objects.select_for_update().get(
        pk=note.sales_invoice_id, company_id=note.company_id,
    )
    for slice_ in slices:
        receipt = (
            CustomerReceipt.objects.select_for_update()
            .filter(pk=slice_.get("receipt_id"), company_id=note.company_id)
            .first()
        )
        if receipt is None or receipt.status != ReceiptStatus.POSTED:
            continue
        want = Decimal(str(slice_.get("amount") or 0))
        outstanding = LedgerService.sales_invoice_outstanding(inv)
        unallocated = Decimal(str(receipt.amount or 0)) - _allocated_of_payment("receipt", receipt)
        apply_amt = min(want, outstanding, unallocated)
        if apply_amt > 0:
            try:
                with transaction.atomic():
                    PaymentService.allocate_receipt(
                        receipt=receipt, sales_invoice=inv, amount=apply_amt, user=user,
                    )
            except (BusinessRuleError, IntegrityError):
                # The receipt was allocated to this invoice again while the credit note stood.
                # That slice is already covered; cancelling the note must not fail over it.
                continue
    note.peeled_receipt_allocations = []
    note.save(update_fields=["peeled_receipt_allocations", "updated_at"])


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
            prior = (
                SalesCreditNoteItem.objects.filter(
                    credit_note__sales_invoice=inv,
                    credit_note__status=SalesCreditNote.Status.COMPLETED,
                    source_item=src,
                )
                .exclude(credit_note_id=note.pk)
                .aggregate(s=Sum("quantity"))["s"]
                or Decimal("0")
            )
            if item.quantity + prior > src.quantity:
                raise BusinessRuleError(
                    f"Credit quantity {item.quantity} exceeds remaining qty "
                    f"{src.quantity - prior} on source line {src.pk}."
                )
        warnings = []
        tax_on = _tax_enabled(inv.invoice_type)
        if tax_on:
            missing_hsn = note.items.filter(hsn_code="").count()
            if missing_hsn:
                if getattr(note.company, "einvoice_enabled", False):
                    raise BusinessRuleError(
                        f"{missing_hsn} line(s) missing HSN — required before completing an e-invoice credit note."
                    )
                warnings.append(
                    f"{missing_hsn} line(s) missing HSN — GSTR Table 12 / e-Invoice may fail."
                )
            # Sec 34(2): CN for GST invoice must be dated on/before 30 Nov of FY
            # following the FY of the original invoice (April–March).
            if note.note_date and inv.invoice_date:
                inv_d = inv.invoice_date
                fy_start = inv_d.year if inv_d.month >= 4 else inv_d.year - 1
                deadline = date(fy_start + 1, 11, 30)
                if note.note_date > deadline:
                    raise BusinessRuleError(
                        "Credit note date is past the Sec 34(2) deadline "
                        "(30 Nov following the FY of the original invoice)."
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
        if extra > Decimal(str(inv.grand_total or 0)):
            raise BusinessRuleError(
                f"Additional debit {extra} exceeds original invoice value {inv.grand_total}."
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
            missing_hsn = note.items.filter(hsn_code="").count()
            if missing_hsn:
                warnings.append(
                    f"{missing_hsn} line(s) missing HSN — GSTR Table 12 / e-Invoice may fail."
                )
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
    def set_order_items(order: SalesOrder, items_data, user):
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
        get_tax_engine(order.company).compute_document_totals(
            order,
            items,
            tax_enabled=_tax_enabled(order.invoice_type),
            intra_state=party_intra_state(
                order.company,
                order.customer.state,
                order.customer.gstin or "",
                supply_type=getattr(order, "supply_type", ""),
            ),
            invoice_discount=order.invoice_discount,
            invoice_discount_mode=order.invoice_discount_mode,
            auto_round_off=order.auto_round_off,
            additional_charges=order.additional_charges,
        )
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
        if order.status != SalesOrder.Status.DRAFT:
            raise BusinessRuleError(f"Cannot confirm an order in status {order.status}.")
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
        if DeliveryChallan.objects.filter(sales_order=order).exclude(
            status=DeliveryChallan.Status.CANCELLED
        ).exists():
            raise BusinessRuleError("This sales order already has a delivery challan.")
        order_lines = list(order.items.select_related("product"))
        requested = SalesNotesService._conversion_quantities(
            order_lines, line_quantities, counter="invoiced_quantity",
        )
        if order.customer.status == Customer.Status.BLOCKED:
            raise BusinessRuleError("Cannot create an invoice for a blocked customer.")
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
            item.invoiced_quantity = Decimal(str(item.invoiced_quantity or 0)) + qty
            item.save(update_fields=["invoiced_quantity"])
        if not items_data:
            raise BusinessRuleError("This sales order already has an invoice.")
        SalesService.set_items(invoice, items_data, user)
        from sales.order_gates import copy_credit_override

        copy_credit_override(order, invoice)
        invoice.source_order = order
        invoice.save(update_fields=["source_order"])
        # Keep a confirmed order confirmed until the invoice Completes when the
        # whole quantity moved. A short convert stays open for the remainder.
        remaining = any(
            Decimal(str(item.invoiced_quantity or 0)) < Decimal(str(item.quantity or 0))
            for item in order_lines
        )
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
                order.status = SalesOrder.Status.CONFIRMED
                fields.append("status")
        order.save(update_fields=fields)

    @staticmethod
    def _conversion_quantities(order_lines, line_quantities, *, counter):
        """Map each line id to the quantity this convert should take.

        Omitted lines take nothing when the caller passed an explicit map.
        A request above the remaining quantity is refused.
        """
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
            remaining = Decimal(str(item.quantity or 0)) - Decimal(str(getattr(item, counter) or 0))
            if remaining < 0:
                remaining = Decimal("0")
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
                raise BusinessRuleError(
                    f"Cannot convert {qty} of '{item.product.name}': "
                    f"only {remaining} is still open on this sales order."
                )
            if qty > 0:
                any_qty = True
            requested[item.pk] = qty
        if explicit and not any_qty:
            raise BusinessRuleError(
                "This sales order already has an invoice."
                if counter == "invoiced_quantity"
                else "This sales order already has a delivery challan."
            )
        return requested

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
        if order.customer.status == Customer.Status.BLOCKED:
            raise BusinessRuleError("Cannot create a delivery challan for a blocked customer.")
        if not order.number:
            order.number = DocumentNumberService.next_number(
                order.company,
                "SALES_ORDER",
                gstin=resolve_series_gstin(order.company),
                on_date=order.order_date,
            )
        if (
            DeliveryChallan.objects.filter(sales_order=order, status=DeliveryChallan.Status.DRAFT)
            .exists()
        ):
            raise BusinessRuleError("This sales order already has a delivery challan.")
        # CR-120: SO already converted to an invoice cannot also become a challan
        # (would double-post stock/AR when both complete).
        if order.converted_invoice_id:
            raise BusinessRuleError(
                "This sales order already has an invoice. Cancel or delete that invoice "
                "before converting to a delivery challan."
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
        order_lines = list(order.items.select_related("product"))
        requested = SalesNotesService._conversion_quantities(
            order_lines, line_quantities, counter="shipped_quantity",
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
            item.shipped_quantity = Decimal(str(item.shipped_quantity or 0)) + qty
            item.save(update_fields=["shipped_quantity"])
        if not items_data:
            raise BusinessRuleError("This sales order already has a delivery challan.")
        SalesNotesService.set_challan_items(challan, items_data, user)
        remaining = any(
            Decimal(str(item.shipped_quantity or 0)) < Decimal(str(item.quantity or 0))
            for item in order_lines
        )
        order.updated_by = user
        update_fields = ["updated_by", "updated_at"]
        if remaining and order.status != SalesOrder.Status.DRAFT:
            order.status = SalesOrder.Status.PARTIALLY_CONVERTED
            update_fields.append("status")
        order.save(update_fields=update_fields)
        return challan

    @staticmethod
    @transaction.atomic
    def cancel_sales_order(order: SalesOrder, user):
        from inventory.services import InventoryService

        order = SalesOrder.objects.select_for_update().get(pk=order.pk, company_id=order.company_id)
        if order.status not in (SalesOrder.Status.DRAFT, SalesOrder.Status.CONFIRMED):
            raise BusinessRuleError(f"Cannot cancel an order in status {order.status}.")
        if order.converted_invoice_id:
            raise BusinessRuleError(
                "Cancel or delete the draft invoice converted from this order first."
            )
        if DeliveryChallan.objects.filter(sales_order=order).exclude(
            status=DeliveryChallan.Status.CANCELLED
        ).exists():
            raise BusinessRuleError(
                "Cancel or reverse outstanding delivery challans before cancelling this order."
            )
        if order.status == SalesOrder.Status.CONFIRMED:
            warehouse = order.warehouse or InventoryService.default_warehouse(order.company)
            for item in order.items.select_related("product"):
                InventoryService.release_reservation(
                    order.company, warehouse, item.product, item.quantity, user
                )
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
        return challan

    @staticmethod
    @transaction.atomic
    def complete_challan(challan: DeliveryChallan, user):
        from inventory.models import MovementType
        from inventory.services import InventoryService, InventoryValuationService

        challan = DeliveryChallan.objects.select_for_update().get(pk=challan.pk)
        if challan.status != DeliveryChallan.Status.DRAFT:
            raise BusinessRuleError(f"Cannot complete challan in status {challan.status}.")
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
        if challan.sales_order_id:
            from .models import SalesOrder

            # CR-094: never mutate another tenant's SO / reservations.
            order = SalesOrder.objects.select_for_update().get(
                pk=challan.sales_order_id,
                company_id=challan.company_id,
            )
            if order.status == SalesOrder.Status.CANCELLED:
                raise BusinessRuleError("Cannot complete a challan for a cancelled sales order.")
            # CR-120: refuse challan complete when SO already linked to an invoice.
            if order.converted_invoice_id:
                raise BusinessRuleError(
                    "Cannot complete a delivery challan for a sales order that already "
                    "has an invoice."
                )
            warehouse = order.warehouse or InventoryService.default_warehouse(challan.company)
            if order.status in (
                SalesOrder.Status.CONFIRMED,
                SalesOrder.Status.PARTIALLY_CONVERTED,
            ):
                challan_qty = {
                    item.product_id: Decimal(str(item.quantity or 0)) for item in items
                }
                order_lines = list(order.items.select_related("product"))
                tracked = any(Decimal(str(row.shipped_quantity or 0)) > 0 for row in order_lines)
                for item in order_lines:
                    release_qty = (
                        challan_qty.get(item.product_id, Decimal("0"))
                        if tracked
                        else Decimal(str(item.quantity or 0))
                    )
                    if release_qty > 0:
                        InventoryService.release_reservation(
                            challan.company, warehouse, item.product, release_qty, user
                        )
            order_lines = list(order.items.all())
            if order_lines and all(
                Decimal(str(row.shipped_quantity or 0)) >= Decimal(str(row.quantity or 0))
                for row in order_lines
            ):
                order.status = SalesOrder.Status.CONVERTED
            elif any(Decimal(str(row.shipped_quantity or 0)) > 0 for row in order_lines):
                order.status = SalesOrder.Status.PARTIALLY_CONVERTED
            else:
                order.status = SalesOrder.Status.CONVERTED
            order.updated_by = user
            order.save(update_fields=["status", "updated_by", "updated_at"])
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
        if challan.customer.status == Customer.Status.BLOCKED:
            raise BusinessRuleError("Cannot create an invoice for a blocked customer.")
        order = challan.sales_order
        # CR-120: refuse second invoice when SO already linked elsewhere.
        if order is not None and order.converted_invoice_id:
            raise BusinessRuleError(
                "This sales order already has an invoice; cannot convert the challan again."
            )
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
            price_mode=getattr(order, "price_mode", None) or SalesInvoice.PriceMode.EXCLUSIVE,
            terms_text=getattr(order, "terms_text", "") if order else "",
            notes=challan.notes or (getattr(order, "notes", "") if order else ""),
            vehicle_number=challan.vehicle_number,
            transporter_name=challan.transporter_name,
            transporter_id=challan.transporter_id,
            transport_distance_km=challan.transport_distance_km,
            created_by=user,
            updated_by=user,
        )
        items_data = [
            {
                "product": item.product,
                "description": item.description,
                "quantity": item.quantity,
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
        ]
        SalesService.set_items(invoice, items_data, user)
        from sales.order_gates import copy_credit_override

        copy_credit_override(order, invoice)
        challan.converted_invoice = invoice
        challan.updated_by = user
        challan.save(update_fields=["converted_invoice", "updated_by", "updated_at"])
        order = challan.sales_order
        # CR-120: if SO already points at a different invoice, refuse linking a second one.
        if order is not None and order.converted_invoice_id and order.converted_invoice_id != invoice.pk:
            raise BusinessRuleError(
                "This sales order already has a different invoice; cannot convert the challan again."
            )
        if order is not None and order.converted_invoice_id is None:
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
            return challan
        if challan.status != DeliveryChallan.Status.COMPLETED:
            raise BusinessRuleError("Only draft or completed challans can be cancelled.")
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
        if (
            order is not None
            and order.status == SalesOrder.Status.CONVERTED
            and order.converted_invoice_id is None
            and not DeliveryChallan.objects.filter(sales_order=order)
            .exclude(pk=challan.pk)
            .exclude(status=DeliveryChallan.Status.CANCELLED)
            .exists()
        ):
            warehouse = order.warehouse or InventoryService.default_warehouse(order.company)
            for item in order.items.select_related("product"):
                InventoryService.reserve_stock(
                    order.company, warehouse, item.product, item.quantity, user
                )
            order.status = SalesOrder.Status.CONFIRMED
            order.updated_by = user
            order.save(update_fields=["status", "updated_by", "updated_at"])
        record_document_event(document=challan, user=user, event="delivery_challan.cancelled")
        return challan
