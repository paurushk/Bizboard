"""RPT-04: every figure on the Sales summary uses one definition (net of credit notes, incl. GST)."""

from decimal import Decimal

import pytest

from tests.test_gst_returns import PERIOD, _setup_gst_month

pytestmark = pytest.mark.django_db

RANGE = {"date_from": f"{PERIOD}-01", "date_to": f"{PERIOD}-31"}


def _summary(tenant, **params):
    resp = tenant.client.get("/api/v1/reports/sales-summary/", {**RANGE, **params})
    assert resp.status_code == 200, resp.content
    body = resp.json()
    return body.get("data", body)


def _d(value):
    return Decimal(str(value))


def test_headline_is_gross_net_of_credit_notes_with_the_breakdown(tenant_a):
    _setup_gst_month(tenant_a)
    t = _summary(tenant_a)["totals"]
    assert _d(t["creditNotes"]) > 0
    assert _d(t["revenue"]) == _d(t["grossInvoiced"]) - _d(t["creditNotes"]) + _d(t["debitNotes"])
    assert _d(t["revenue"]) - _d(t["taxable"]) == _d(t["gstAndOther"])
    assert _d(t["gstAndOther"]) > 0


def test_revenue_by_date_adds_up_to_the_headline(tenant_a):
    _setup_gst_month(tenant_a)
    data = _summary(tenant_a)
    by_date_total = sum(_d(r["revenue"]) for r in data["byDate"])
    assert by_date_total == _d(data["totals"]["revenue"])


def test_top_customers_use_the_same_figure_as_the_headline(tenant_a):
    _setup_gst_month(tenant_a)
    data = _summary(tenant_a)
    # top lists are capped at ten rows; the fixture has fewer customers than that
    assert sum(_d(r["amount"]) for r in data["topCustomers"]) == _d(data["totals"]["revenue"])


def test_summary_rejects_a_range_longer_than_the_limit(tenant_a):
    resp = tenant_a.client.get(
        "/api/v1/reports/sales-summary/", {"date_from": "2020-01-01", "date_to": "2026-12-31"},
    )
    assert resp.status_code == 400


@pytest.mark.invariant_skip("gl.ar_ties_to_documents", reason="sales documents or journals are built through the ORM, so receivables in the ledger and on documents cannot tie")
def test_sales_summary_agrees_with_the_dashboard_and_leaves_out_opening_dues(tenant_a):
    """The dashboard's "sales this month" and the Sales screen must be the same number for the same days,
    and an opening-balance invoice (a due brought in, not a sale) counts in neither."""
    from django.utils import timezone

    from reporting.services import ReportService
    from sales.models import SalesInvoice
    from tests.conftest import make_customer

    customer = make_customer(tenant_a.company, name="Opening Co")
    today = timezone.localdate()
    SalesInvoice.objects.bulk_create([
        SalesInvoice(
            company=tenant_a.company, customer=customer, status=SalesInvoice.Status.COMPLETED,
            invoice_type=SalesInvoice.InvoiceType.NON_GST, invoice_date=today,
            taxable_total=Decimal("500.00"), grand_total=Decimal("500.00"), is_opening_balance=True,
        ),
        SalesInvoice(
            company=tenant_a.company, customer=customer, status=SalesInvoice.Status.COMPLETED,
            invoice_type=SalesInvoice.InvoiceType.NON_GST, invoice_date=today,
            taxable_total=Decimal("200.00"), grand_total=Decimal("200.00"),
        ),
    ])
    dash = ReportService.dashboard(tenant_a.company)["sales_this_month"]["total"]
    totals = ReportService.sales_totals(tenant_a.company, today.replace(day=1), today)
    assert totals["revenue"] == Decimal(str(dash)) == Decimal("200.00")
    tops = ReportService.customer_sales(tenant_a.company, today.replace(day=1), today)["rows"]
    assert sum(r["amount"] for r in tops) == Decimal("200.00")
