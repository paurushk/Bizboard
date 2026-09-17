"""HTTP-level coverage for the new report endpoints: permission gating and
routing/URL wiring, complementing the direct ReportService-level tests in
test_discount_report.py / test_invoice_profit_report.py."""

from __future__ import annotations

from decimal import Decimal

import pytest

from accounts.models import CompanyUser
from sales.models import SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product, make_supplier

pytestmark = pytest.mark.django_db


def _completed_invoice(tenant, qty="2", price="1000", discount_percent="0"):
    product = make_product(tenant.company, gst_rate="18")
    add_stock(tenant, product, "20")
    customer = make_customer(tenant.company)
    draft = create_draft_invoice(
        tenant,
        customer,
        [
            {
                "product": product.id,
                "quantity": qty,
                "unit_price": price,
                "gst_rate": "18",
                "discount_percent": discount_percent,
            }
        ],
    )
    resp = tenant.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert resp.status_code == 200, resp.data
    return SalesInvoice.objects.get(pk=draft["id"]), product, customer


def test_sales_discount_report_endpoint_returns_expected_shape(tenant_a):
    _completed_invoice(tenant_a, discount_percent="10")
    resp = tenant_a.client.get("/api/v1/reports/sales-discounts/")
    assert resp.status_code == 200, resp.data
    assert resp.data["totals"]["invoice_count"] == 1
    assert Decimal(str(resp.data["totals"]["line_discount_total"])) == Decimal("200.00")
    assert resp.data["by_party"][0]["invoices"] == 1


def test_purchase_discount_report_endpoint_returns_expected_shape(tenant_a):
    supplier = make_supplier(tenant_a.company)
    product = make_product(tenant_a.company, gst_rate="18")
    resp = tenant_a.client.post(
        "/api/v1/purchases/invoices/",
        {
            "supplier": supplier.id,
            "purchase_type": "GST",
            "items": [
                {"product": product.id, "quantity": "5", "unit_price": "200", "gst_rate": "18", "discount_percent": "5"}
            ],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    complete = tenant_a.client.post(f"/api/v1/purchases/invoices/{resp.data['id']}/complete/")
    assert complete.status_code == 200, complete.data

    resp = tenant_a.client.get("/api/v1/reports/purchase-discounts/")
    assert resp.status_code == 200, resp.data
    assert resp.data["totals"]["invoice_count"] == 1
    assert Decimal(str(resp.data["totals"]["line_discount_total"])) == Decimal("50.00")


def test_invoice_profit_report_endpoint_returns_snapshot_rows(tenant_a):
    invoice, _, customer = _completed_invoice(tenant_a)
    resp = tenant_a.client.get("/api/v1/reports/invoice-profit/")
    assert resp.status_code == 200, resp.data
    assert resp.data["totals"]["invoice_count"] == 1
    row = resp.data["rows"][0]
    assert row["invoice_id"] == invoice.pk
    assert row["customer"] == customer.name


def test_invoice_profit_rollup_endpoint_group_by_customer(tenant_a):
    _completed_invoice(tenant_a)
    resp = tenant_a.client.get("/api/v1/reports/invoice-profit/rollup/?group_by=customer")
    assert resp.status_code == 200, resp.data
    assert len(resp.data["rows"]) == 1
    assert resp.data["rows"][0]["invoices"] == 1


def test_invoice_profit_rollup_endpoint_rejects_bad_group_by(tenant_a):
    resp = tenant_a.client.get("/api/v1/reports/invoice-profit/rollup/?group_by=bogus")
    assert resp.status_code == 400


def test_invoice_profit_report_rejects_oversized_date_span(tenant_a):
    resp = tenant_a.client.get(
        "/api/v1/reports/invoice-profit/?date_from=2020-01-01&date_to=2025-01-01"
    )
    assert resp.status_code == 400


def test_staff_without_financial_reports_permission_cannot_view_invoice_profit(tenant_a):
    membership = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.staff)
    membership.can_view_financial_reports = False
    membership.save(update_fields=["can_view_financial_reports"])

    resp = tenant_a.staff_client.get("/api/v1/reports/invoice-profit/")
    assert resp.status_code == 403


def test_staff_without_financial_reports_permission_cannot_view_discount_report(tenant_a):
    membership = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.staff)
    membership.can_view_financial_reports = False
    membership.save(update_fields=["can_view_financial_reports"])

    resp = tenant_a.staff_client.get("/api/v1/reports/sales-discounts/")
    assert resp.status_code == 403
