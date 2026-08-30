"""Sales credit/debit notes, orders, and delivery challans (Phase 1 / 1.5)."""

from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.events import emit
from core.exceptions import BusinessRuleError
from core.services.billing import compute_document_totals
from core.services.document_numbers import DocumentNumberService, resolve_series_gstin
from core.services.place_of_supply import assert_place_of_supply_for_gst, party_intra_state
from ledgers.services import LedgerService
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
    SalesReturn,
)
from .services import SalesService, _build_items, _tax_enabled, _validate_lines


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
    return party_intra_state(inv.company, inv.customer.state, inv.customer.gstin or "")


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
        inv = note.sales_invoice
        compute_document_totals(
            note,
            items,
            tax_enabled=_tax_enabled(inv.invoice_type),
            intra_state=_invoice_intra_state(inv),
            invoice_discount=note.invoice_discount,
            invoice_discount_mode=note.invoice_discount_mode,
            auto_round_off=note.auto_round_off,
            additional_charges=Decimal(str(getattr(note, "additional_charges", 0) or 0)),
        )
        SalesCreditNoteItem.objects.bulk_create(items)
        note.updated_by = user
        note.save()
        return note

    @staticmethod
    @transaction.atomic
    def complete_credit_note(note: SalesCreditNote, user):
        note = SalesCreditNote.objects.select_for_update().get(pk=note.pk)
        if note.status != SalesCreditNote.Status.DRAFT:
            raise BusinessRuleError(f"Cannot complete credit note in status {note.status}.")
        if not note.items.exists():
            raise BusinessRuleError("Cannot complete a credit note without line items.")
        from reporting.gst_periods import assert_period_allows_money_amend, mark_period_dirty_if_snapshotted

        assert_period_allows_money_amend(note.company, note.note_date)
        inv = note.sales_invoice
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
        for item in note.items.select_related("source_item"):
            src = item.source_item
            if src is None:
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
        emit("document.completed", document=note, user=user, event="sales_credit_note.completed")
        emit("sales_credit_note.completed", document=note, user=user)
        return note, warnings

    @staticmethod
    @transaction.atomic
    def cancel_credit_note(note: SalesCreditNote, user):
        note = SalesCreditNote.objects.select_for_update().get(pk=note.pk)
        if note.status != SalesCreditNote.Status.COMPLETED:
            raise BusinessRuleError("Only completed credit notes can be cancelled.")
        from reporting.gst_periods import assert_period_allows_money_amend, mark_period_dirty_if_snapshotted

        assert_period_allows_money_amend(note.company, note.note_date)
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
        inv = note.sales_invoice
        compute_document_totals(
            note,
            items,
            tax_enabled=_tax_enabled(inv.invoice_type),
            intra_state=_invoice_intra_state(inv),
            invoice_discount=note.invoice_discount,
            invoice_discount_mode=note.invoice_discount_mode,
            auto_round_off=note.auto_round_off,
            additional_charges=Decimal(str(getattr(note, "additional_charges", 0) or 0)),
        )
        SalesDebitNoteItem.objects.bulk_create(items)
        note.updated_by = user
        note.save()
        return note

    @staticmethod
    @transaction.atomic
    def complete_debit_note(note: SalesDebitNote, user, *, confirm_additional_debit: bool = False):
        note = SalesDebitNote.objects.select_for_update().get(pk=note.pk)
        if note.status != SalesDebitNote.Status.DRAFT:
            raise BusinessRuleError(f"Cannot complete debit note in status {note.status}.")
        if not note.items.exists():
            raise BusinessRuleError("Cannot complete a debit note without line items.")
        inv = note.sales_invoice
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
        if extra > 0 and not confirm_additional_debit:
            raise BusinessRuleError(
                f"Debit note {note.grand_total} exceeds credit-note headroom {max(cn_headroom, Decimal('0'))}. "
                "Pass confirm_additional_debit=true to bill an additional amount on the original invoice."
            )
        if extra > Decimal(str(inv.grand_total or 0)):
            raise BusinessRuleError(
                f"Additional debit {extra} exceeds original invoice value {inv.grand_total}."
            )
        warnings = []
        if _tax_enabled(inv.invoice_type):
            missing_hsn = note.items.filter(hsn_code="").count()
            if missing_hsn:
                warnings.append(
                    f"{missing_hsn} line(s) missing HSN — GSTR Table 12 / e-Invoice may fail."
                )
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
        emit("document.completed", document=note, user=user, event="sales_debit_note.completed")
        emit("sales_debit_note.completed", document=note, user=user)
        return note, warnings

    @staticmethod
    @transaction.atomic
    def cancel_debit_note(note: SalesDebitNote, user):
        note = SalesDebitNote.objects.select_for_update().get(pk=note.pk)
        if note.status != SalesDebitNote.Status.COMPLETED:
            raise BusinessRuleError("Only completed debit notes can be cancelled.")
        from reporting.gst_periods import assert_period_allows_money_amend, mark_period_dirty_if_snapshotted

        assert_period_allows_money_amend(note.company, note.note_date)
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
        return note

    # ---------- Sales orders ----------

    @staticmethod
    @transaction.atomic
    def set_order_items(order: SalesOrder, items_data, user):
        if order.status != SalesOrder.Status.DRAFT:
            raise BusinessRuleError("Converted, confirmed, or cancelled orders cannot be edited.")
        items_data = _normalize_items(items_data, order.company)
        _validate_lines(items_data, order.company, check_active=True)
        order.items.all().delete()
        items = _build_items(SalesOrderItem, "sales_order", order, items_data)
        compute_document_totals(
            order,
            items,
            tax_enabled=_tax_enabled(order.invoice_type),
            intra_state=party_intra_state(
                order.company, order.customer.state, order.customer.gstin or ""
            ),
            invoice_discount=order.invoice_discount,
            invoice_discount_mode=order.invoice_discount_mode,
            auto_round_off=order.auto_round_off,
            additional_charges=order.additional_charges,
        )
        SalesOrderItem.objects.bulk_create(items)
        order.updated_by = user
        order.save()
        return order

    @staticmethod
    @transaction.atomic
    def confirm_sales_order(order: SalesOrder, user):
        """DRAFT → CONFIRMED; reserve each line at the company default warehouse."""
        from inventory.services import InventoryService

        order = SalesOrder.objects.select_for_update().get(pk=order.pk)
        if order.status != SalesOrder.Status.DRAFT:
            raise BusinessRuleError(f"Cannot confirm an order in status {order.status}.")
        items = list(order.items.select_related("product"))
        if not items:
            raise BusinessRuleError("Cannot confirm an order without line items.")
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
    @transaction.atomic
    def convert_sales_order(order: SalesOrder, user):
        from inventory.services import InventoryService

        order = SalesOrder.objects.select_for_update().get(pk=order.pk)
        if order.status not in (SalesOrder.Status.DRAFT, SalesOrder.Status.CONFIRMED):
            raise BusinessRuleError(f"Cannot convert an order in status {order.status}.")
        if order.customer.status == Customer.Status.BLOCKED:
            raise BusinessRuleError("Cannot create an invoice for a blocked customer.")
        if not order.number:
            order.number = DocumentNumberService.next_number(
                order.company,
                "SALES_ORDER",
                gstin=resolve_series_gstin(order.company),
                on_date=order.order_date,
            )
        # Confirmed orders hold reservations; release before invoice SALE posts on_hand.
        if order.status == SalesOrder.Status.CONFIRMED:
            warehouse = order.warehouse or InventoryService.default_warehouse(order.company)
            for item in order.items.select_related("product"):
                InventoryService.release_reservation(
                    order.company, warehouse, item.product, item.quantity, user
                )
        invoice = SalesInvoice.objects.create(
            company=order.company,
            customer=order.customer,
            warehouse=order.warehouse or InventoryService.default_warehouse(order.company),
            invoice_type=order.invoice_type,
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
                # BB-000732: preserve lot/serial identity through conversion.
                "batch": getattr(item, "batch", None),
                "batch_no": getattr(item, "batch_no", "") or "",
                "serial_numbers": getattr(item, "serial_numbers", None) or [],
            }
            for item in order.items.select_related("product")
        ]
        SalesService.set_items(invoice, items_data, user)
        order.status = SalesOrder.Status.CONVERTED
        order.converted_invoice = invoice
        order.updated_by = user
        order.save()
        return invoice

    @staticmethod
    @transaction.atomic
    def convert_sales_order_to_challan(order: SalesOrder, user):
        from .models import DeliveryChallan
        from inventory.services import InventoryService

        order = SalesOrder.objects.select_for_update().get(pk=order.pk)
        if order.status not in (SalesOrder.Status.DRAFT, SalesOrder.Status.CONFIRMED):
            raise BusinessRuleError(f"Cannot convert an order in status {order.status}.")
        if order.customer.status == Customer.Status.BLOCKED:
            raise BusinessRuleError("Cannot create a delivery challan for a blocked customer.")
        if not order.number:
            order.number = DocumentNumberService.next_number(
                order.company,
                "SALES_ORDER",
                gstin=resolve_series_gstin(order.company),
                on_date=order.order_date,
            )
        live_challan = (
            DeliveryChallan.objects.filter(sales_order=order)
            .exclude(status=DeliveryChallan.Status.CANCELLED)
            .exists()
        )
        if live_challan:
            raise BusinessRuleError("This sales order already has a delivery challan.")
        if order.status == SalesOrder.Status.CONFIRMED:
            order.status = SalesOrder.Status.CONVERTED
            order.save(update_fields=["status"])
        challan = DeliveryChallan.objects.create(
            company=order.company,
            customer=order.customer,
            warehouse=order.warehouse or InventoryService.default_warehouse(order.company),
            sales_order=order,
            challan_date=timezone.localdate(),
            notes=order.notes,
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
                "batch": getattr(item, "batch", None),
                "batch_no": getattr(item, "batch_no", "") or "",
                "serial_numbers": getattr(item, "serial_numbers", None) or [],
            }
            for item in order.items.select_related("product")
        ]
        SalesNotesService.set_challan_items(challan, items_data, user)
        order.status = SalesOrder.Status.CONVERTED
        order.updated_by = user
        order.save(update_fields=["status", "updated_by", "updated_at"])
        return challan

    @staticmethod
    @transaction.atomic
    def cancel_sales_order(order: SalesOrder, user):
        from inventory.services import InventoryService

        order = SalesOrder.objects.select_for_update().get(pk=order.pk)
        if order.status not in (SalesOrder.Status.DRAFT, SalesOrder.Status.CONFIRMED):
            raise BusinessRuleError(f"Cannot cancel an order in status {order.status}.")
        if order.status == SalesOrder.Status.CONFIRMED:
            warehouse = order.warehouse or InventoryService.default_warehouse(order.company)
            for item in order.items.select_related("product"):
                InventoryService.release_reservation(
                    order.company, warehouse, item.product, item.quantity, user
                )
        order.status = SalesOrder.Status.CANCELLED
        order.updated_by = user
        order.save()
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
        compute_document_totals(
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
        # BB-000729: series keyed by GSTIN + FY (primary GSTIN when challan has no stamp).
        challan.number = challan.number or DocumentNumberService.next_number(
            challan.company,
            "DELIVERY_CHALLAN",
            gstin=resolve_series_gstin(challan.company),
            on_date=challan.challan_date,
        )
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
        challan.status = DeliveryChallan.Status.COMPLETED
        challan.completed_at = timezone.now()
        challan.pdf_status = SalesInvoice.PdfStatus.QUEUED
        challan.stock_posted = stock_posted
        challan.updated_by = user
        challan.save()
        if challan.sales_order:
            warehouse = challan.sales_order.warehouse or InventoryService.default_warehouse(challan.company)
            for item in challan.sales_order.items.select_related("product"):
                InventoryService.release_reservation(
                    challan.company, warehouse, item.product, item.quantity, user
                )
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
        # BB-000342 / BB-000399: composition/unregistered → NON_GST (Bill of Supply), not GST.
        from accounts.models import Company
        from inventory.services import InventoryService

        reg = challan.company.registration_type
        if reg == Company.RegistrationType.REGULAR and challan.company.gstin:
            invoice_type = SalesInvoice.InvoiceType.GST
        else:
            invoice_type = SalesInvoice.InvoiceType.NON_GST
        invoice = SalesInvoice.objects.create(
            company=challan.company,
            customer=challan.customer,
            warehouse=challan.warehouse or InventoryService.default_warehouse(challan.company),
            invoice_type=invoice_type,
            notes=challan.notes,
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
                # BB-000732: preserve lot/serial identity through conversion.
                "batch": getattr(item, "batch", None),
                "batch_no": getattr(item, "batch_no", "") or "",
                "serial_numbers": getattr(item, "serial_numbers", None) or [],
            }
            for item in challan.items.select_related("product")
        ]
        SalesService.set_items(invoice, items_data, user)
        challan.converted_invoice = invoice
        challan.updated_by = user
        challan.save(update_fields=["converted_invoice", "updated_by", "updated_at"])
        order = challan.sales_order
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
        if challan.status != DeliveryChallan.Status.COMPLETED:
            raise BusinessRuleError("Only completed challans can be cancelled.")
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
        return challan
