"""Phase 1 Regressions: CR-122, CR-145, CR-146."""

from datetime import date
from decimal import Decimal

import pytest

from core.exceptions import BusinessRuleError
from ledgers.services import LedgerService
from purchases.models import PurchaseInvoice
from reporting.services import ReportService
from sales.models import DeliveryChallan, SalesInvoice, SalesOrder
from sales.notes_services import SalesNotesService
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db


def test_cr122_so_with_challan_cannot_be_edited_or_deleted(tenant_a):
    company = tenant_a.company
    product = make_product(company, selling_price="100", gst_rate="0")
    customer = make_customer(company)
    order = SalesOrder.objects.create(
        company=company,
        customer=customer,
        order_date=date(2026, 4, 1),
        status=SalesOrder.Status.DRAFT,
        invoice_type="NON_GST",
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    SalesNotesService.set_order_items(
        order,
        [{"product": product, "quantity": Decimal("2"), "unit_price": Decimal("100"), "gst_rate": 0}],
        tenant_a.owner,
    )
    # Convert to delivery challan
    SalesNotesService.convert_sales_order_to_challan(order, tenant_a.owner)

    # Attempt to edit via API
    resp = tenant_a.client.patch(
        f"/api/v1/sales/orders/{order.id}/",
        {"notes": "Updated note"},
        format="json",
    )
    assert resp.status_code == 400, resp.data
    assert "delivery challan" in str(resp.data).lower()

    # Attempt to delete via API
    del_resp = tenant_a.client.delete(f"/api/v1/sales/orders/{order.id}/")
    assert del_resp.status_code == 400, del_resp.data
    assert "delivery challan" in str(del_resp.data).lower()


def test_cr145_opening_balance_invoices_excluded_from_aging_and_kpis(tenant_a):
    company = tenant_a.company
    product = make_product(
        company,
        purchase_price="100",
        selling_price="200",
        gst_rate="0",
    )
    add_stock(tenant_a, product, qty="10", unit_cost="100")
    customer = make_customer(company)
    supplier = make_supplier(company)

    # 1. Normal sales invoice
    inv_data = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "200", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv_data['id']}/complete/")
    assert resp.status_code == 200, resp.data

    # 2. Opening balance sales invoice
    open_inv_data = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "500", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    open_inv = SalesInvoice.objects.get(pk=open_inv_data["id"])
    open_inv.is_opening_balance = True
    open_inv.save(update_fields=["is_opening_balance"])
    open_resp = tenant_a.client.post(f"/api/v1/sales/invoices/{open_inv.id}/complete/")
    assert open_resp.status_code == 200, open_resp.data

    # Receivables aging & dashboard receivables should reflect ONLY the normal invoice (200), not the opening (500)
    rec_aging = ReportService.receivables_aging(company)
    assert ReportService._aging_total(rec_aging) == Decimal("200.00")
    assert ReportService._company_receivables(company) == Decimal("200.00")

    # 3. Normal purchase invoice
    pur_data = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur_data['id']}/complete/").status_code == 200

    # 4. Opening balance purchase invoice
    open_pur_data = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "300", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    open_pur = PurchaseInvoice.objects.get(pk=open_pur_data["id"])
    open_pur.is_opening_balance = True
    open_pur.save(update_fields=["is_opening_balance"])
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{open_pur.id}/complete/").status_code == 200

    # Payables aging & dashboard payables should reflect ONLY the normal purchase (100), not the opening (300)
    pay_aging = ReportService.payables_aging(company)
    assert ReportService._aging_total(pay_aging) == Decimal("100.00")
    assert ReportService._company_payables(company) == Decimal("100.00")


def test_cr146_supplier_outstanding_foots_documents_when_accounting_on(tenant_a):
    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])

    supplier = make_supplier(company)
    product = make_product(company, purchase_price="150", gst_rate="0")

    pur_data = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "2", "unit_price": "150", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur_data['id']}/complete/").status_code == 200

    outstanding = LedgerService.supplier_outstanding(company, supplier)
    assert outstanding == Decimal("300.00")
