"""QOS-0003 — a real large-tenant fixture for the sales register / CSV export.

The existing performance suite (test_ws08_report_performance.py) deliberately
avoids literal bulk creation ("creating 5000+ real invoices would be far too
slow") and instead lowers the guard threshold to test the guard logic. That's
the right call for the *fast* unit lane. This file is the executed, real-scale
counterpart QOS-0003 asks for: bulk_create (not the full completion workflow —
sales_register only reads flat invoice + customer fields, so a raw row insert
is a faithful, honest large-tenant fixture for this specific report) 50,000
COMPLETED invoices spread across one year, then exercise the register/export
the way a 50k-invoice tenant actually would.

Discovery while building this: ReportService already hard-caps a single
register query at MAX_REGISTER_ROWS_HARD_CAP (10,000) regardless of
date_from — a full-year pull on a 50k tenant is *supposed* to be rejected,
not silently materialise 50k rows. So the honest "does this scale" test has
two halves: the full-year pull is correctly refused, and a realistic
sub-window (a month, comfortably under the cap) stays fast with a flat query
count. Not a soak or concurrency test — see QOS-0006 for that.
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core.exceptions import BusinessRuleError
from reporting.services import MAX_REGISTER_ROWS_HARD_CAP, ReportService
from reporting.views import EXPORTS
from sales.models import SalesInvoice
from tests.conftest import make_customer

pytestmark = pytest.mark.django_db

LARGE_TENANT_ROWS = 50_000
YEAR_START = date(2026, 1, 1)
YEAR_END = YEAR_START + timedelta(days=365)
# ~137/day over the year -> comfortably under MAX_REGISTER_ROWS_HARD_CAP for
# any single month, the realistic query shape for a report screen.
MONTH_START = date(2026, 6, 1)
MONTH_END = date(2026, 6, 30)


def _bulk_invoices(company, customer, n: int):
    return [
        SalesInvoice(
            company=company,
            customer=customer,
            status=SalesInvoice.Status.COMPLETED,
            invoice_type=SalesInvoice.InvoiceType.NON_GST,
            invoice_date=YEAR_START + timedelta(days=i % 365),
            taxable_total=Decimal("1000.00"),
            grand_total=Decimal("1000.00"),
        )
        for i in range(n)
    ]


@pytest.fixture
def large_tenant(tenant_a):
    customer = make_customer(tenant_a.company)
    SalesInvoice.objects.bulk_create(_bulk_invoices(tenant_a.company, customer, LARGE_TENANT_ROWS), batch_size=2000)
    assert SalesInvoice.objects.filter(company=tenant_a.company).count() == LARGE_TENANT_ROWS
    return tenant_a


@pytest.mark.slow
@pytest.mark.no_invariant_check  # bulk_create bypasses ledger/GL posting on purpose - a raw report fixture, not a real financial write path
def test_full_year_pull_on_50k_tenant_is_refused_not_silently_slow(large_tenant):
    """The hard cap must fire for a genuinely oversized single query — a
    50k-invoice year is exactly the case QOS-0003 worried would go
    unnoticed until a real deploy."""
    with pytest.raises(BusinessRuleError, match=str(MAX_REGISTER_ROWS_HARD_CAP)):
        ReportService.sales_register(large_tenant.company, date_from=YEAR_START, date_to=YEAR_END)


@pytest.mark.slow
@pytest.mark.no_invariant_check  # bulk_create bypasses ledger/GL posting on purpose - a raw report fixture, not a real financial write path
def test_realistic_month_window_stays_flat_and_fast_on_a_50k_tenant(large_tenant):
    """The query shape a report screen actually uses (a bounded window, not
    the whole year) must stay fast and its query count must not depend on
    how many invoices the *rest* of the tenant's year holds."""
    # A near-empty tenant is the baseline "flat" is measured against.
    small_customer = make_customer(large_tenant.company, name="Small Co")
    SalesInvoice.objects.bulk_create(_bulk_invoices(large_tenant.company, small_customer, 5))
    with CaptureQueriesContext(connection) as small:
        ReportService.sales_register(
            large_tenant.company, date_from=MONTH_START, date_to=MONTH_END, customer_id=small_customer.id,
        )

    start = time.perf_counter()
    with CaptureQueriesContext(connection) as large:
        result = ReportService.sales_register(large_tenant.company, date_from=MONTH_START, date_to=MONTH_END)
    elapsed = time.perf_counter() - start

    assert len(result["rows"]) > 0
    assert len(result["rows"]) < MAX_REGISTER_ROWS_HARD_CAP
    # Query count must not scale with the tenant's total row count — same
    # handful of statements (main select, aggregate, credit-note scan,
    # debit-note scan) whether the tenant has 5 or 50,000 invoices overall.
    assert len(large.captured_queries) <= len(small.captured_queries) + 2, (
        f"query count grew with tenant size: small={len(small.captured_queries)} "
        f"large={len(large.captured_queries)}"
    )
    # Generous budget — a smoke floor, not a strict perf gate; it exists to
    # catch an accidental N+1 or an unbounded in-Python join, not to pin
    # exact hardware-dependent timing.
    assert elapsed < 5.0, f"one month's register on a 50k-invoice tenant took {elapsed:.2f}s (budget 5s)"


@pytest.mark.slow
@pytest.mark.no_invariant_check  # bulk_create bypasses ledger/GL posting on purpose - a raw report fixture, not a real financial write path
def test_csv_export_of_a_realistic_window_completes_on_a_50k_tenant(large_tenant):
    params = {"date_from": MONTH_START.isoformat(), "date_to": MONTH_END.isoformat()}
    start = time.perf_counter()
    rows = EXPORTS["sales-register"](large_tenant.company, params)
    elapsed = time.perf_counter() - start

    assert 0 < len(rows) < MAX_REGISTER_ROWS_HARD_CAP
    assert elapsed < 5.0, f"sales-register CSV row-build for a month on a 50k-invoice tenant took {elapsed:.2f}s (budget 5s)"
