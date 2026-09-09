"""A15 — CR-090+ re-verification fixes."""

from datetime import date
from decimal import Decimal

import pytest

from accounting.models import JournalEntry
from core.exceptions import BusinessRuleError
from ledgers.services import LedgerService
from payments.models import CustomerReceipt, PaymentAllocation, ReceiptStatus
from purchases.boe_services import BillOfEntryService
from purchases.models import BillOfEntry, PurchaseCreditNote, PurchaseInvoice
from purchases.services import PurchaseService
from reporting.services import ReportService
from sales.models import SalesOrder
from tests.conftest import (
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db


def test_cr094_delivery_challan_rejects_cross_company_sales_order(tenant_a, tenant_b):
    product = make_product(tenant_a.company)
    customer_a = make_customer(tenant_a.company)
    customer_b = make_customer(tenant_b.company)
    foreign_so = SalesOrder.objects.create(
        company=tenant_b.company,
        customer=customer_b,
        order_date=date(2026, 4, 1),
        status=SalesOrder.Status.CONFIRMED,
        created_by=tenant_b.owner,
        updated_by=tenant_b.owner,
    )
    resp = tenant_a.client.post(
        "/api/v1/sales/delivery-challans/",
        {
            "customer": customer_a.id,
            "sales_order": foreign_so.id,
            "items": [
                {"product": product.id, "quantity": "1", "unit_price": "10", "gst_rate": "0"}
            ],
        },
        format="json",
    )
    assert resp.status_code == 400, resp.data
    assert "sales_order" in str(resp.data).lower() or "invalid" in str(resp.data).lower()


def test_cr100_purchase_invoice_outstanding_ignores_receipt_allocations(tenant_a):
    product = make_product(tenant_a.company, purchase_price="100", gst_rate="0")
    supplier = make_supplier(tenant_a.company)
    pur = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200
    inv = PurchaseInvoice.objects.get(pk=pur["id"])
    customer = make_customer(tenant_a.company)
    receipt = CustomerReceipt.objects.create(
        company=tenant_a.company,
        customer=customer,
        amount=Decimal("40.00"),
        receipt_date=inv.invoice_date,
        status=ReceiptStatus.POSTED,
        mode="CASH",
        created_by=tenant_a.owner,
    )
    PaymentAllocation.objects.create(
        company=tenant_a.company,
        purchase_invoice=inv,
        receipt=receipt,
        amount=Decimal("40.00"),
        created_by=tenant_a.owner,
    )
    assert LedgerService.purchase_invoice_outstanding(inv) == inv.grand_total
    assert LedgerService.bulk_purchase_invoice_outstanding(
        tenant_a.company, [inv.id]
    )[inv.id] == inv.grand_total


def test_cr101_dashboard_payables_equals_aging_sum(tenant_a):
    product = make_product(tenant_a.company, purchase_price="250", gst_rate="0")
    supplier = make_supplier(tenant_a.company)
    pur = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "250", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200
    aging = ReportService.payables_aging(tenant_a.company)
    dash = ReportService._company_payables(tenant_a.company)
    assert dash == ReportService._aging_total(aging)
    assert dash == PurchaseInvoice.objects.get(pk=pur["id"]).grand_total


def test_cr097_purchase_cancel_blocked_when_draft_credit_note_exists(tenant_a):
    product = make_product(tenant_a.company, purchase_price="100", gst_rate="0")
    supplier = make_supplier(tenant_a.company)
    pur = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200
    inv = PurchaseInvoice.objects.get(pk=pur["id"])
    cn = tenant_a.client.post(
        "/api/v1/purchases/credit-notes/",
        {
            "supplier": supplier.id,
            "purchase_invoice": inv.id,
            "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "10", "gst_rate": "0"}],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    assert PurchaseCreditNote.objects.get(pk=cn.data["id"]).status == PurchaseCreditNote.Status.DRAFT
    with pytest.raises(BusinessRuleError, match="draft credit/debit"):
        PurchaseService.cancel(inv, tenant_a.owner)


def test_cr098_boe_cancel_unlinks_draft_purchase(tenant_a):
    supplier = make_supplier(tenant_a.company)
    boe = BillOfEntry.objects.create(
        company=tenant_a.company,
        supplier=supplier,
        boe_number="BOE-CR098",
        boe_date=date(2026, 4, 1),
        status=BillOfEntry.Status.DRAFT,
        created_by=tenant_a.owner,
    )
    pi = PurchaseInvoice.objects.create(
        company=tenant_a.company,
        supplier=supplier,
        invoice_date=date(2026, 4, 1),
        status=PurchaseInvoice.Status.DRAFT,
        bill_of_entry=boe,
        grand_total=Decimal("0"),
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    BillOfEntryService.cancel(boe, tenant_a.owner)
    pi.refresh_from_db()
    assert pi.bill_of_entry_id is None
    boe.refresh_from_db()
    assert boe.status == BillOfEntry.Status.CANCELLED


def test_cr103_empty_posted_je_not_treated_as_done(tenant_a):
    from accounting.management.commands.backfill_missing_postings import _has_je

    JournalEntry.objects.create(
        company=tenant_a.company,
        entry_date=date(2026, 4, 1),
        source_type="SALES_INVOICE",
        source_id=999001,
        purpose="COMPLETE",
        status=JournalEntry.Status.POSTED,
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    assert _has_je(tenant_a.company, "SALES_INVOICE", 999001, "COMPLETE") is False
