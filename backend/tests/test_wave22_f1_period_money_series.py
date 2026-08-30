"""Wave 22 Sprint F1 — period gates, money dating, CN series order."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest

from accounting.models import JournalEntry
from accounting.services import seed_chart_of_accounts
from core.exceptions import BusinessRuleError
from core.models import DocumentSeries
from core.services.document_numbers import DocumentNumberService, fy_label_for
from payments.services import PaymentService
from reporting.gst_periods import soft_close_period
from sales.models import NoteReason, SalesCreditNote, SalesInvoice
from sales.notes_services import SalesNotesService
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _complete_invoice(tenant, *, unit_price="100"):
    product = make_product(tenant.company, sku="F1-INV")
    add_stock(tenant, product, "10")
    customer = make_customer(tenant.company)
    inv = create_draft_invoice(
        tenant,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": unit_price, "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    assert tenant.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    return SalesInvoice.objects.get(pk=inv["id"]), customer, product


def test_bb_000699_period_exception_aborts_sales_complete(tenant_a):
    """Non-BRE from period helpers must abort Complete (no except-pass swallow)."""
    product = make_product(tenant_a.company, sku="F1-699")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "50", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    with patch(
        "reporting.gst_periods.assert_period_allows_money_amend",
        side_effect=RuntimeError("injected period failure"),
    ):
        resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 500
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    assert invoice.status == SalesInvoice.Status.DRAFT
    assert not invoice.number


def test_bb_000699_business_rule_still_blocks_soft_closed(tenant_a):
    soft_close_period(tenant_a.company, "2026-04", tenant_a.owner)
    product = make_product(tenant_a.company, sku="F1-699B")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "50", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    SalesInvoice.objects.filter(pk=inv["id"]).update(invoice_date=date(2026, 4, 15))
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 400
    assert "SOFT_CLOSED" in str(resp.data).upper() or "closed" in str(resp.data).lower()
    assert SalesInvoice.objects.get(pk=inv["id"]).status == SalesInvoice.Status.DRAFT


def test_bb_000700_create_receipt_gated_by_period(tenant_a):
    soft_close_period(tenant_a.company, "2026-03", tenant_a.owner)
    customer = make_customer(tenant_a.company)
    with pytest.raises(BusinessRuleError, match="SOFT_CLOSED|closed"):
        PaymentService.create_receipt(
            company=tenant_a.company,
            customer=customer,
            amount=Decimal("100"),
            mode="CASH",
            receipt_date=date(2026, 3, 10),
            user=tenant_a.owner,
        )


def test_bb_000701_unallocate_reverse_uses_original_je_date(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company)
    invoice, customer, _product = _complete_invoice(tenant_a, unit_price="50")
    receipt = PaymentService.create_receipt(
        company=tenant_a.company,
        customer=customer,
        amount=Decimal("50"),
        mode="CASH",
        receipt_date=date(2026, 1, 15),
        user=tenant_a.owner,
    )
    alloc = PaymentService.allocate_receipt(
        receipt=receipt,
        sales_invoice=invoice,
        amount=Decimal("50"),
        user=tenant_a.owner,
    )
    alloc_je = JournalEntry.objects.get(
        source_type="PAYMENT_ALLOCATION",
        source_id=alloc.id,
        purpose="ALLOCATE_RECEIPT",
        status=JournalEntry.Status.POSTED,
    )
    assert alloc_je.entry_date == date(2026, 1, 15)

    PaymentService.reverse_allocation(allocation=alloc, user=tenant_a.owner)
    reversal = JournalEntry.objects.get(
        company=tenant_a.company,
        source_type="JOURNAL_REVERSAL",
        source_id=alloc_je.id,
        purpose="REVERSE",
        status=JournalEntry.Status.POSTED,
    )
    assert reversal.entry_date == date(2026, 1, 15)


def test_bb_000736_cn_period_before_next_number(tenant_a):
    """Closed-period CN Complete must not allocate a document number."""
    soft_close_period(tenant_a.company, "2026-02", tenant_a.owner)
    invoice, customer, product = _complete_invoice(tenant_a, unit_price="200")
    invoice.invoice_date = date(2026, 1, 15)
    invoice.save(update_fields=["invoice_date"])
    note = SalesCreditNote.objects.create(
        company=tenant_a.company,
        customer=customer,
        sales_invoice=invoice,
        note_date=date(2026, 2, 10),
        reason=NoteReason.OTHERS,
        reason_detail="F1 period order",
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    SalesNotesService.set_credit_note_items(
        note,
        [
            {
                "product": product,
                "quantity": Decimal("1"),
                "unit_price": Decimal("50"),
                "discount_percent": Decimal("0"),
                "gst_rate": Decimal("0"),
            }
        ],
        tenant_a.owner,
    )
    before = list(
        DocumentSeries.objects.filter(
            company=tenant_a.company, doc_type="SALES_CREDIT_NOTE"
        ).values_list("gstin_key", "fy_label", "next_number")
    )
    with pytest.raises(BusinessRuleError, match="SOFT_CLOSED|closed"):
        SalesNotesService.complete_credit_note(note, tenant_a.owner)
    note.refresh_from_db()
    assert note.status == SalesCreditNote.Status.DRAFT
    assert not note.number
    after = list(
        DocumentSeries.objects.filter(
            company=tenant_a.company, doc_type="SALES_CREDIT_NOTE"
        ).values_list("gstin_key", "fy_label", "next_number")
    )
    assert after == before
    # Successful path (open period) must key series by GSTIN/FY when identity present.
    note.note_date = date(2026, 8, 1)
    note.save(update_fields=["note_date"])
    SalesNotesService.complete_credit_note(note, tenant_a.owner)
    note.refresh_from_db()
    assert note.status == SalesCreditNote.Status.COMPLETED
    assert note.number
    assert DocumentSeries.objects.filter(
        company=tenant_a.company,
        doc_type="SALES_CREDIT_NOTE",
        fy_label=fy_label_for(tenant_a.company, note.note_date),
    ).exists() or DocumentNumberService.peek(
        tenant_a.company, "SALES_CREDIT_NOTE", on_date=note.note_date
    )
