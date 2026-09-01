"""Purchase credit/debit notes (recorded) and purchase orders (Phase 1 / 1.5)."""

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.events import emit
from core.exceptions import BusinessRuleError
from core.services.billing import apply_rcm_memo_after_tax, compute_document_totals
from core.services.document_numbers import DocumentNumberService, resolve_series_gstin
from core.services.place_of_supply import party_intra_state
from masters.models import Product

from .models import (
    PurchaseCreditNote,
    PurchaseCreditNoteItem,
    PurchaseDebitNote,
    PurchaseDebitNoteItem,
    PurchaseInvoice,
    PurchaseOrder,
    PurchaseOrderItem,
)
from .services import PurchaseService, _validate_lines


def _tax_enabled(purchase_type) -> bool:
    return purchase_type != PurchaseInvoice.PurchaseType.NON_GST


def _invoice_intra_state(inv) -> bool:
    if inv is None:
        return True
    if Decimal(str(inv.igst_total or 0)) > 0:
        return False
    if Decimal(str(inv.cgst_total or 0)) + Decimal(str(inv.sgst_total or 0)) > 0:
        return True
    return party_intra_state(inv.company, inv.supplier.state, inv.supplier.gstin or "")


def _purchase_note_headroom(inv, *, exclude_cn_id=None, exclude_dn_id=None, for_dn=False) -> Decimal:
    prior_cns = (
        PurchaseCreditNote.objects.filter(
            purchase_invoice=inv, status=PurchaseCreditNote.Status.COMPLETED
        )
        .exclude(pk=exclude_cn_id)
        .aggregate(total=Sum("grand_total"))["total"]
        or Decimal("0")
    )
    prior_dns = (
        PurchaseDebitNote.objects.filter(
            purchase_invoice=inv, status=PurchaseDebitNote.Status.COMPLETED
        )
        .exclude(pk=exclude_dn_id)
        .aggregate(total=Sum("grand_total"))["total"]
        or Decimal("0")
    )
    inv_total = Decimal(str(inv.grand_total or 0))
    prior_cns = Decimal(str(prior_cns))
    prior_dns = Decimal(str(prior_dns))
    if for_dn:
        return inv_total - prior_dns + prior_cns
    return inv_total - prior_cns + prior_dns


def _apply_rcm_memo_if_linked(note, items) -> None:
    """BB-000336: if the linked purchase invoice is reverse-charge, the note's
    value legs must also be RCM (memo taxable/tax, zero GST on the note itself)
    so GL/GSTR reverse RCM payable/ITC rather than normal Input GST/AP.
    PurchaseCreditNote/PurchaseDebitNote have no is_reverse_charge column of
    their own — set it transiently so apply_rcm_memo_after_tax (generic on
    document.is_reverse_charge) applies the same two-pass memo as invoices.
    """
    invoice = getattr(note, "purchase_invoice", None)
    note.is_reverse_charge = bool(invoice and getattr(invoice, "is_reverse_charge", False))
    if note.is_reverse_charge:
        apply_rcm_memo_after_tax(note, items)


def _resolve_purchase_source_item(line, company_id, invoice_id=None):
    """Resolve and tenant-check a CN/DN source PurchaseItem, or return None."""
    from .models import PurchaseItem

    source_item = line.get("source_item")
    if source_item is None and line.get("source_item_id") is not None:
        source_item = line.get("source_item_id")
    if source_item is None:
        return None
    if isinstance(source_item, (int, str)):
        try:
            item = PurchaseItem.objects.get(pk=int(source_item), invoice__company_id=company_id)
        except (PurchaseItem.DoesNotExist, TypeError, ValueError) as exc:
            raise BusinessRuleError("source_item does not belong to this company.") from exc
        if invoice_id is not None and item.invoice_id != invoice_id:
            raise BusinessRuleError("source_item does not belong to this invoice.")
        return item
    if getattr(source_item, "invoice_id", None) is not None:
        if not PurchaseItem.objects.filter(pk=source_item.pk, invoice__company_id=company_id).exists():
            raise BusinessRuleError("source_item does not belong to this company.")
        if invoice_id is not None and source_item.invoice_id != invoice_id:
            raise BusinessRuleError("source_item does not belong to this invoice.")
    return source_item


def _normalize_items(items_data, company, invoice_id=None):
    out = []
    for line in items_data:
        d = dict(line)
        product = d.get("product")
        if not isinstance(product, Product):
            d["product"] = Product.objects.get(pk=product, company=company)
        if "source_item" in d or "source_item_id" in d:
            d["source_item"] = _resolve_purchase_source_item(d, company.id, invoice_id=invoice_id)
        out.append(d)
    return out


def _build_note_items(model_cls, parent_field, parent, items_data):
    from core.services.uqc import snapshot_unit_fields

    product_ids = [line["product"].pk for line in items_data]
    products = {
        p.pk: p
        for p in Product.objects.filter(pk__in=product_ids).select_related("unit")
    }
    # PurchaseOrderItem has no HSN/UQC snapshot columns (invoice/CN/DN lines do).
    items = []
    for line in items_data:
        product = products.get(line["product"].pk, line["product"])
        kwargs = {
            parent_field: parent,
            "company_id": parent.company_id,
            "product": product,
            "description": line.get("description") or product.name,
            "quantity": line["quantity"],
            "unit_price": line.get("unit_price", product.purchase_price),
            "discount_percent": line.get("discount_percent", Decimal("0")),
            "gst_rate": line.get("gst_rate", product.gst_rate),
            "cess_rate": line.get("cess_rate", Decimal("0")),
            "cess_amount": line.get("cess_amount", Decimal("0")),
        }
        if hasattr(model_cls, "hsn_code"):
            snap = snapshot_unit_fields(product, line)
            kwargs.update({
                "hsn_code": snap["hsn_code"],
                "unit_name": snap["unit_name"],
                "uqc_code": snap["uqc_code"],
            })
        # BB-000364: preserve lineage/HSN from the originating invoice line
        # (product master HSN may have since changed) when the caller supplies it.
        if hasattr(model_cls, "source_item") and line.get("source_item") is not None:
            kwargs["source_item"] = line["source_item"]
        items.append(model_cls(**kwargs))
    return items


class PurchaseNotesService:
    @staticmethod
    @transaction.atomic
    def set_credit_note_items(note: PurchaseCreditNote, items_data, user):
        if note.status != PurchaseCreditNote.Status.DRAFT:
            raise BusinessRuleError("Completed credit note cannot be edited.")
        items_data = _normalize_items(
            items_data, note.company, invoice_id=note.purchase_invoice_id,
        )
        _validate_lines(items_data, note.company)
        note.items.all().delete()
        items = _build_note_items(PurchaseCreditNoteItem, "credit_note", note, items_data)
        tax_enabled = True
        if note.purchase_invoice_id:
            tax_enabled = _tax_enabled(note.purchase_invoice.purchase_type)
        compute_document_totals(
            note,
            items,
            tax_enabled=tax_enabled,
            intra_state=_invoice_intra_state(note.purchase_invoice) if note.purchase_invoice_id else party_intra_state(
                note.company, note.supplier.state, note.supplier.gstin or ""
            ),
            invoice_discount=note.invoice_discount,
            invoice_discount_mode=note.invoice_discount_mode,
            auto_round_off=note.auto_round_off,
            additional_charges=Decimal(str(getattr(note, "additional_charges", 0) or 0)),
        )
        _apply_rcm_memo_if_linked(note, items)
        PurchaseCreditNoteItem.objects.bulk_create(items)
        note.updated_by = user
        note.save()
        return note

    @staticmethod
    @transaction.atomic
    def complete_credit_note(note: PurchaseCreditNote, user):
        note = PurchaseCreditNote.objects.select_for_update().get(pk=note.pk)
        if note.status != PurchaseCreditNote.Status.DRAFT:
            raise BusinessRuleError(f"Cannot complete credit note in status {note.status}.")
        if not note.items.exists():
            raise BusinessRuleError("Cannot complete a credit note without line items.")
        if note.company.is_gst_registered and not note.purchase_invoice_id:
            raise BusinessRuleError(
                "GST-registered companies must link purchase credit notes to a purchase invoice."
            )
        # BB-000339: cap to the linked invoice's remaining outstanding, mirroring
        # SalesNotesService.complete_credit_note — a CN cannot relieve more AP
        # than is actually still owed on the invoice.
        if note.purchase_invoice_id:
            max_cn = _purchase_note_headroom(note.purchase_invoice, exclude_cn_id=note.pk)
            if note.grand_total > max_cn:
                raise BusinessRuleError(
                    f"Credit note {note.grand_total} exceeds invoice remaining outstanding {max_cn}."
                )
        warnings = []
        tax_enabled = True
        if note.purchase_invoice_id:
            tax_enabled = _tax_enabled(note.purchase_invoice.purchase_type)
        if tax_enabled:
            missing_hsn = note.items.filter(hsn_code="").count()
            if missing_hsn:
                warnings.append(
                    f"{missing_hsn} line(s) missing HSN — GSTR Table 12 / e-Invoice may fail."
                )
        # BB-000736 / BB-000699: period before number; no except-pass.
        from reporting.gst_periods import assert_period_allows_money_amend, mark_period_dirty_if_snapshotted

        assert_period_allows_money_amend(note.company, note.note_date)
        stamp = getattr(note.purchase_invoice, "company_gstin", None) if note.purchase_invoice_id else None
        note.number = note.number or DocumentNumberService.next_number(
            note.company,
            "PURCHASE_CREDIT_NOTE",
            gstin=resolve_series_gstin(note.company, stamp),
            on_date=note.note_date,
        )
        note.status = PurchaseCreditNote.Status.COMPLETED
        note.completed_at = timezone.now()
        note.updated_by = user
        note.save()
        mark_period_dirty_if_snapshotted(note.company, note.note_date)
        if note.company.accounting_enabled:
            from accounting.services import PostingService

            PostingService.post_note(
                note, source_type="PURCHASE_CREDIT_NOTE", direction="PURCHASE_CREDIT", user=user
            )
        emit("document.completed", document=note, user=user, event="purchase_credit_note.completed")
        return note, warnings

    @staticmethod
    @transaction.atomic
    def cancel_credit_note(note: PurchaseCreditNote, user):
        note = PurchaseCreditNote.objects.select_for_update().get(pk=note.pk)
        if note.status != PurchaseCreditNote.Status.COMPLETED:
            raise BusinessRuleError("Only completed credit notes can be cancelled.")
        from reporting.gst_periods import assert_period_allows_money_amend, mark_period_dirty_if_snapshotted

        assert_period_allows_money_amend(note.company, note.note_date)
        if note.company.accounting_enabled:
            from accounting.models import JournalEntry
            from accounting.services import PostingService
            entry = JournalEntry.objects.filter(company=note.company, source_type="PURCHASE_CREDIT_NOTE",
                source_id=note.id, purpose="COMPLETE", status=JournalEntry.Status.POSTED).first()
            if entry:
                PostingService.reverse(entry, user, note.note_date)
        note.status = PurchaseCreditNote.Status.CANCELLED
        note.cancelled_at = timezone.now()
        note.updated_by = user
        note.save()
        mark_period_dirty_if_snapshotted(note.company, note.note_date)
        return note

    @staticmethod
    @transaction.atomic
    def set_debit_note_items(note: PurchaseDebitNote, items_data, user):
        if note.status != PurchaseDebitNote.Status.DRAFT:
            raise BusinessRuleError("Completed debit note cannot be edited.")
        items_data = _normalize_items(
            items_data, note.company, invoice_id=note.purchase_invoice_id,
        )
        _validate_lines(items_data, note.company)
        note.items.all().delete()
        items = _build_note_items(PurchaseDebitNoteItem, "debit_note", note, items_data)
        tax_enabled = True
        if note.purchase_invoice_id:
            tax_enabled = _tax_enabled(note.purchase_invoice.purchase_type)
        compute_document_totals(
            note,
            items,
            tax_enabled=tax_enabled,
            intra_state=_invoice_intra_state(note.purchase_invoice) if note.purchase_invoice_id else party_intra_state(
                note.company, note.supplier.state, note.supplier.gstin or ""
            ),
            invoice_discount=note.invoice_discount,
            invoice_discount_mode=note.invoice_discount_mode,
            auto_round_off=note.auto_round_off,
            additional_charges=Decimal(str(getattr(note, "additional_charges", 0) or 0)),
        )
        _apply_rcm_memo_if_linked(note, items)
        PurchaseDebitNoteItem.objects.bulk_create(items)
        note.updated_by = user
        note.save()
        return note

    @staticmethod
    @transaction.atomic
    def complete_debit_note(note: PurchaseDebitNote, user):
        note = PurchaseDebitNote.objects.select_for_update().get(pk=note.pk)
        if note.status != PurchaseDebitNote.Status.DRAFT:
            raise BusinessRuleError(f"Cannot complete debit note in status {note.status}.")
        if not note.items.exists():
            raise BusinessRuleError("Cannot complete a debit note without line items.")
        if note.company.is_gst_registered and not note.purchase_invoice_id:
            raise BusinessRuleError(
                "GST-registered companies must link purchase debit notes to a purchase invoice."
            )
        if note.purchase_invoice_id:
            headroom = _purchase_note_headroom(
                note.purchase_invoice, exclude_dn_id=note.pk, for_dn=True
            )
            if note.grand_total > headroom:
                inv = note.purchase_invoice
                raise BusinessRuleError(
                    f"Debit note {note.grand_total} exceeds remaining headroom {headroom} "
                    f"(invoice {inv.grand_total})."
                )
        warnings = []
        tax_enabled = True
        if note.purchase_invoice_id:
            tax_enabled = _tax_enabled(note.purchase_invoice.purchase_type)
        if tax_enabled:
            missing_hsn = note.items.filter(hsn_code="").count()
            if missing_hsn:
                warnings.append(
                    f"{missing_hsn} line(s) missing HSN — GSTR Table 12 / e-Invoice may fail."
                )
        # BB-000736 / BB-000699: period before number; no except-pass.
        from reporting.gst_periods import assert_period_allows_money_amend, mark_period_dirty_if_snapshotted

        assert_period_allows_money_amend(note.company, note.note_date)
        stamp = getattr(note.purchase_invoice, "company_gstin", None) if note.purchase_invoice_id else None
        note.number = note.number or DocumentNumberService.next_number(
            note.company,
            "PURCHASE_DEBIT_NOTE",
            gstin=resolve_series_gstin(note.company, stamp),
            on_date=note.note_date,
        )
        note.status = PurchaseDebitNote.Status.COMPLETED
        note.completed_at = timezone.now()
        note.updated_by = user
        note.save()
        mark_period_dirty_if_snapshotted(note.company, note.note_date)
        if note.company.accounting_enabled:
            from accounting.services import PostingService

            PostingService.post_note(
                note, source_type="PURCHASE_DEBIT_NOTE", direction="PURCHASE_DEBIT", user=user
            )
        emit("document.completed", document=note, user=user, event="purchase_debit_note.completed")
        return note, warnings

    @staticmethod
    @transaction.atomic
    def cancel_debit_note(note: PurchaseDebitNote, user):
        note = PurchaseDebitNote.objects.select_for_update().get(pk=note.pk)
        if note.status != PurchaseDebitNote.Status.COMPLETED:
            raise BusinessRuleError("Only completed debit notes can be cancelled.")
        from reporting.gst_periods import assert_period_allows_money_amend, mark_period_dirty_if_snapshotted

        assert_period_allows_money_amend(note.company, note.note_date)
        if note.company.accounting_enabled:
            from accounting.models import JournalEntry
            from accounting.services import PostingService
            entry = JournalEntry.objects.filter(company=note.company, source_type="PURCHASE_DEBIT_NOTE",
                source_id=note.id, purpose="COMPLETE", status=JournalEntry.Status.POSTED).first()
            if entry:
                PostingService.reverse(entry, user, note.note_date)
        note.status = PurchaseDebitNote.Status.CANCELLED
        note.cancelled_at = timezone.now()
        note.updated_by = user
        note.save()
        mark_period_dirty_if_snapshotted(note.company, note.note_date)
        return note

    @staticmethod
    @transaction.atomic
    def set_order_items(order: PurchaseOrder, items_data, user):
        if order.status != PurchaseOrder.Status.DRAFT:
            raise BusinessRuleError("Converted or cancelled orders cannot be edited.")
        items_data = _normalize_items(items_data, order.company)
        _validate_lines(items_data, order.company)
        order.items.all().delete()
        items = _build_note_items(PurchaseOrderItem, "purchase_order", order, items_data)
        compute_document_totals(
            order,
            items,
            tax_enabled=_tax_enabled(order.purchase_type),
            intra_state=party_intra_state(
                order.company, order.supplier.state, order.supplier.gstin or ""
            ),
            invoice_discount=order.invoice_discount,
            invoice_discount_mode=order.invoice_discount_mode,
            auto_round_off=order.auto_round_off,
            additional_charges=order.additional_charges,
        )
        PurchaseOrderItem.objects.bulk_create(items)
        order.updated_by = user
        order.save()
        return order

    @staticmethod
    @transaction.atomic
    def convert_purchase_order(order: PurchaseOrder, user):
        order = PurchaseOrder.objects.select_for_update().get(pk=order.pk)
        if order.status != PurchaseOrder.Status.DRAFT:
            raise BusinessRuleError(f"Cannot convert an order in status {order.status}.")
        if not order.supplier.is_active:
            raise BusinessRuleError("Cannot create a purchase for an inactive supplier.")
        if not order.number:
            order.number = DocumentNumberService.next_number(
                order.company,
                "PURCHASE_ORDER",
                gstin=resolve_series_gstin(order.company),
                on_date=order.order_date,
            )
        purchase = PurchaseInvoice.objects.create(
            company=order.company,
            supplier=order.supplier,
            purchase_type=order.purchase_type,
            payment_terms_days=order.payment_terms_days,
            additional_charges=order.additional_charges,
            invoice_discount=order.invoice_discount,
            invoice_discount_mode=order.invoice_discount_mode,
            auto_round_off=order.auto_round_off,
            notes=order.notes,
            terms_text=order.terms_text,
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
            }
            for item in order.items.select_related("product")
        ]
        PurchaseService.set_items(purchase, items_data, user)
        order.status = PurchaseOrder.Status.CONVERTED
        order.converted_purchase = purchase
        order.updated_by = user
        order.save()
        return purchase

    @staticmethod
    @transaction.atomic
    def cancel_purchase_order(order: PurchaseOrder, user):
        if order.status != PurchaseOrder.Status.DRAFT:
            raise BusinessRuleError(f"Cannot cancel an order in status {order.status}.")
        order.status = PurchaseOrder.Status.CANCELLED
        order.updated_by = user
        order.save()
        return order
