"""Coverage for the invoice profit report/rollup endpoints (reporting/services.py)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from reporting.services import ReportService
from sales.models import SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _complete(tenant, *, product, customer, qty="2", price="1000"):
    draft = create_draft_invoice(
        tenant, customer, [{"product": product.id, "quantity": qty, "unit_price": price, "gst_rate": "18"}]
    )
    resp = tenant.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert resp.status_code == 200, resp.data
    return SalesInvoice.objects.get(pk=draft["id"])


def test_invoice_profit_report_lists_flat_rows_with_margin(tenant_a):
    product = make_product(tenant_a.company, gst_rate="18")
    add_stock(tenant_a, product, "20")
    customer = make_customer(tenant_a.company)
    invoice = _complete(tenant_a, product=product, customer=customer)

    report = ReportService.invoice_profit_report(tenant_a.company)
    assert report["totals"]["invoice_count"] == 1
    row = report["rows"][0]
    assert row["invoice_id"] == invoice.pk
    assert row["revenue_pre_discount"] == Decimal("2000.00")
    assert row["gross_margin"] == row["revenue_pre_discount"] - row["cogs_total"]
    assert row["cost_basis"] in ("FIFO", "VALUATION_FALLBACK")
    assert row["cogs_total"] > 0


def test_invoice_profit_report_excludes_cancelled_by_default(tenant_a):
    product = make_product(tenant_a.company, gst_rate="18")
    add_stock(tenant_a, product, "20")
    customer = make_customer(tenant_a.company)
    invoice = _complete(tenant_a, product=product, customer=customer)
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice.pk}/cancel/")
    assert resp.status_code == 200, resp.data

    report = ReportService.invoice_profit_report(tenant_a.company)
    assert report["totals"]["invoice_count"] == 0

    report_with_status = ReportService.invoice_profit_report(tenant_a.company, status="CANCELLED")
    assert report_with_status["totals"]["invoice_count"] == 1


def test_invoice_profit_rollup_by_customer_and_product(tenant_a):
    product = make_product(tenant_a.company, gst_rate="18")
    add_stock(tenant_a, product, "20")
    customer = make_customer(tenant_a.company)
    _complete(tenant_a, product=product, customer=customer, qty="2", price="1000")

    by_customer = ReportService.invoice_profit_rollup(tenant_a.company, "customer")
    row = next(r for r in by_customer["rows"] if r["id"] == customer.id)
    assert row["revenue"] == Decimal("2000.00")
    assert row["margin"] == row["revenue"] - row["cogs"]
    assert row["invoices"] == 1

    by_product = ReportService.invoice_profit_rollup(tenant_a.company, "product")
    prow = next(r for r in by_product["rows"] if r["id"] == product.id)
    assert prow["revenue"] == Decimal("2000.00")
    assert prow["margin"] == prow["revenue"] - prow["cogs"]

    by_period = ReportService.invoice_profit_rollup(tenant_a.company, "period")
    assert len(by_period["rows"]) == 1

    by_cost_center = ReportService.invoice_profit_rollup(tenant_a.company, "cost_center")
    assert len(by_cost_center["rows"]) == 1


def test_invoice_profit_rollup_rejects_unknown_group_by(tenant_a):
    from core.exceptions import BusinessRuleError

    with pytest.raises(BusinessRuleError):
        ReportService.invoice_profit_rollup(tenant_a.company, "bogus")
