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
