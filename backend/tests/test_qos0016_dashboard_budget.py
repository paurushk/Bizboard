"""QOS-0016 — observe dashboard render time with a realistic-ish row count.

Not a signed SLO. Catches accidental N+1 on the KPI query. 50k soak stays in
test_qos0003 (marked slow).
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from decimal import Decimal

import pytest

from reporting.services import ReportService
from sales.models import SalesInvoice
from tests.conftest import make_customer

pytestmark = pytest.mark.django_db

N = 400
START = date(2026, 1, 1)


@pytest.mark.no_invariant_check  # bulk_create is a report fixture, not a posted chain
def test_qos0016_dashboard_observation_budget(tenant_a):
    customer = make_customer(tenant_a.company)
    SalesInvoice.objects.bulk_create(
        [
            SalesInvoice(
                company=tenant_a.company,
                customer=customer,
                status=SalesInvoice.Status.COMPLETED,
                invoice_type=SalesInvoice.InvoiceType.NON_GST,
                invoice_date=START + timedelta(days=i % 180),
                taxable_total=Decimal("100.00"),
                grand_total=Decimal("100.00"),
            )
            for i in range(N)
        ],
        batch_size=200,
    )
    start = time.perf_counter()
    payload = ReportService.dashboard(tenant_a.company)
    elapsed = time.perf_counter() - start
    assert "receivables" in payload
    assert elapsed < 5.0, f"dashboard took {elapsed:.2f}s on {N} invoices (observation budget 5s)"


def _seed_year(company, count: int) -> None:
    customers = [make_customer(company) for _ in range(5)]
    SalesInvoice.objects.bulk_create(
        [
            SalesInvoice(
                company=company,
                customer=customers[i % len(customers)],
                status=SalesInvoice.Status.COMPLETED,
                invoice_type=SalesInvoice.InvoiceType.NON_GST,
                invoice_date=START + timedelta(days=i % 365),
                taxable_total=Decimal("100.00"),
                grand_total=Decimal("100.00"),
            )
            for i in range(count)
        ],
        batch_size=200,
    )


@pytest.mark.no_invariant_check  # bulk_create is a report fixture, not a posted chain
def test_qos0016_dashboard_twelve_month_budget_and_flat_query_count(tenant_a):
    """12 months of invoices: inside the time budget, and the query count must not grow with rows."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    _seed_year(tenant_a.company, 300)
    with CaptureQueriesContext(connection) as small:
        ReportService.dashboard(tenant_a.company)

    _seed_year(tenant_a.company, 1200)
    with CaptureQueriesContext(connection) as large:
        start = time.perf_counter()
        payload = ReportService.dashboard(tenant_a.company)
        elapsed = time.perf_counter() - start

    assert "receivables" in payload
    assert len(large) == len(small), (
        f"dashboard queries grew with data: {len(small)} at 300 rows, {len(large)} at 1500 rows"
    )
    assert elapsed < 5.0, f"dashboard took {elapsed:.2f}s on 12 months / 1500 invoices (observation budget 5s)"


@pytest.mark.no_invariant_check  # bulk_create is a report fixture, not a posted chain
def test_dashboard_query_count_at_300_is_under_twice_the_count_at_100(tenant_a):
    """100 vs 300 completed invoices. Counts are recorded after the SQLite run.

    An N+1 would roughly triple the query count. The ceiling is the 300-invoice
    count plus 10 percent, so a later absolute blow-up still fails. This is not
    an SLO and does not close QOS-0016.
    """
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from ledgers.services import LedgerService

    company = tenant_a.company
    _seed_year(company, 100)
    with CaptureQueriesContext(connection) as at_100:
        payload_100 = ReportService.dashboard(company)
    _seed_year(company, 200)
    with CaptureQueriesContext(connection) as at_300:
        payload_300 = ReportService.dashboard(company)

    assert "receivables" in payload_100 and "receivables" in payload_300
    # Relative guard: an N+1 that walks each invoice would roughly triple.
    assert len(at_300) < 2 * max(len(at_100), 1), (
        f"query count at 300 ({len(at_300)}) is not under twice the count at 100 ({len(at_100)})"
    )
    # Absolute ceiling. Raised only when a deliberate query is added and the
    # new count is written here. 80 is above a flat dashboard and below an N+1.
    assert len(at_300) <= 80, f"300-invoice dashboard used {len(at_300)} queries (ceiling 80)"
    invoice_ids = list(
        SalesInvoice.objects.filter(company=company, status=SalesInvoice.Status.COMPLETED).values_list("id", flat=True)
    )
    expected = sum(
        LedgerService.bulk_sales_invoice_outstanding(company, invoice_ids=invoice_ids).values(),
        Decimal("0"),
    )
    assert Decimal(str(payload_300["receivables"])) == expected
