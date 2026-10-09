"""Profit details for one invoice. Snapshot gross margin is left alone."""

from decimal import Decimal

import pytest

from sales.models import SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _two_lines(tenant):
    goods = make_product(tenant.company, sku="PRF-G", name="Goods", gst_rate="18", purchase_price="80")
    other = make_product(tenant.company, sku="PRF-O", name="Other", gst_rate="18", purchase_price="40")
    add_stock(tenant, goods, "20", unit_cost="80")
    add_stock(tenant, other, "20", unit_cost="40")
    customer = make_customer(tenant.company, name="Profit Buyer", state="Karnataka")
    draft = create_draft_invoice(tenant, customer, [
        {"product": goods.id, "quantity": "2", "unit_price": "100", "gst_rate": "18"},
        {"product": other.id, "quantity": "1", "unit_price": "50", "gst_rate": "18"},
    ])
    return draft


def test_two_lines_foot_the_profit_formula(tenant_a):
    draft = _two_lines(tenant_a)
    preview = tenant_a.client.get(f"/api/v1/sales/invoices/{draft['id']}/profit-details/")
    assert preview.status_code == 200, preview.data
    assert preview.data["estimated"] is True
    goods = next(row for row in preview.data["lines"] if row["name"] == "Goods")
    assert Decimal(str(goods["unit_cost"])) == Decimal("80")
    assert goods["fell_back_to_purchase_price"] is False

    done = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert done.status_code == 200, done.data
    resp = tenant_a.client.get(f"/api/v1/sales/invoices/{draft['id']}/profit-details/")
    assert resp.status_code == 200, resp.data
    data = resp.data
    assert data["estimated"] is False
    assert data["formula"] == "Profit = Sales amount − Total cost − GST collected"
    sales_amount = Decimal(str(data["sales_amount"]))
    total_cost = Decimal(str(data["total_cost"]))
    tax_payable = Decimal(str(data["tax_payable"]))
    profit = Decimal(str(data["profit"]))
    assert profit == sales_amount - total_cost - tax_payable
    assert sum(Decimal(str(row["line_cost"])) for row in data["lines"]) == total_cost
    invoice = SalesInvoice.objects.get(pk=draft["id"])
    assert sales_amount == invoice.grand_total - invoice.additional_charges
    assert tax_payable == invoice.cgst_total + invoice.sgst_total + invoice.igst_total + invoice.cess_total
    goods = next(row for row in data["lines"] if row["name"] == "Goods")
    assert Decimal(str(goods["unit_cost"])) == Decimal("80")
    assert Decimal(str(goods["quantity"])) == Decimal("2")
    assert Decimal(str(goods["line_cost"])) == Decimal("160")
    assert goods["fell_back_to_purchase_price"] is False


def test_additional_charges_are_excluded_from_sales_amount(tenant_a):
    product = make_product(tenant_a.company, sku="PRF-CHG", gst_rate="0")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    draft = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "200", "gst_rate": "0"}],
        invoice_type="NON_GST",
        additional_charges="50",
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert done.status_code == 200, done.data
    invoice = SalesInvoice.objects.get(pk=draft["id"])
    resp = tenant_a.client.get(f"/api/v1/sales/invoices/{draft['id']}/profit-details/")
    assert resp.status_code == 200, resp.data
    assert Decimal(str(resp.data["sales_amount"])) == invoice.grand_total - Decimal("50")
    assert invoice.additional_charges == Decimal("50.00")
    assert Decimal(str(resp.data["sales_amount"])) != invoice.grand_total


def test_reverse_charge_tax_payable_is_zero(tenant_a):
    product = make_product(tenant_a.company, sku="PRF-RCM", gst_rate="18", hsn_code="1001")
    add_stock(tenant_a, product, "5")
    customer = make_customer(
        tenant_a.company, name="RCM Buyer", state="Karnataka", gstin="29AABCU9603R1ZJ",
    )
    draft = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18", "hsn_code": "1001"}],
        is_reverse_charge=True,
    )
    done = tenant_a.client.post(
        f"/api/v1/sales/invoices/{draft['id']}/complete/",
        {"confirm_sales_rcm": True},
        format="json",
    )
    assert done.status_code == 200, done.data
    resp = tenant_a.client.get(f"/api/v1/sales/invoices/{draft['id']}/profit-details/")
    assert resp.status_code == 200, resp.data
    assert Decimal(str(resp.data["tax_payable"])) == Decimal("0")
    sales_amount = Decimal(str(resp.data["sales_amount"]))
    total_cost = Decimal(str(resp.data["total_cost"]))
    assert Decimal(str(resp.data["profit"])) == sales_amount - total_cost


def test_inv_det_07_staff_without_financial_reports_gets_403(tenant_a):
    product = make_product(tenant_a.company, sku="PRF-STAFF", gst_rate="0")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    draft = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    resp = tenant_a.staff_client.get(f"/api/v1/sales/invoices/{draft['id']}/profit-details/")
    assert resp.status_code == 403
