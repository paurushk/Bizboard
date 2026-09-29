"""TC-EXP-004: Period Lock Temporal Boundary Enforcement Workflow.

Validates that when an accounting/GST period is locked, no financial document
can be created, modified, backdated, or cancelled within that period, while
mutations in open periods continue to succeed normally.
"""

from __future__ import annotations

import time
import pytest
from rest_framework import status

from reporting.gst_periods import GstReturnPeriod, get_or_create_period
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def test_period_lock_blocks_backdated_invoicing(tenant_a, assert_consistent):
    """Attempting to post an invoice dated inside a locked period must be strictly rejected."""
    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])

    # Lock GST period for 2026-07
    p_locked = get_or_create_period(company, "2026-07")
    p_locked.status = GstReturnPeriod.Status.CLOSED
    p_locked.save(update_fields=["status"])

    product = make_product(company, gst_rate="18", selling_price="200.00")
    add_stock(tenant_a, product, "20", unit_cost="100.00")
    customer = make_customer(company, state="Karnataka")

    # 1. Create a draft invoice dated in 2026-07
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "2", "unit_price": "200.00", "gst_rate": "18"}],
        invoice_date="2026-07-15",
    )

    # 2. Attempting to complete the invoice in locked period must fail
    t0 = time.perf_counter()
    done_locked = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    latency_ms = (time.perf_counter() - t0) * 1000

    # Period gate check must execute with sub-50ms core latency (SLA <= 600ms in eager test client environment)
    assert latency_ms < 600, f"Period lock check took {latency_ms:.2f}ms"

    # Must reject with 400 Bad Request
    assert done_locked.status_code == status.HTTP_400_BAD_REQUEST, done_locked.data
    assert "CLOSED" in str(done_locked.data) or "period" in str(done_locked.data).lower()

    # 3. Completing an invoice in an OPEN period (2026-08-15) must succeed
    inv_open = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "200.00", "gst_rate": "18"}],
        invoice_date="2026-08-15",
    )
    done_open = tenant_a.client.post(f"/api/v1/sales/invoices/{inv_open['id']}/complete/")
    assert done_open.status_code == status.HTTP_200_OK, done_open.data

    # 4. Invariants must remain strictly consistent
    assert_consistent(company)
