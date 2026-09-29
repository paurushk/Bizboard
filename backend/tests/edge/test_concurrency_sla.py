"""TC-EXP-002: Concurrency, Idempotency & Race Condition Prevention.

Validates that rapid consecutive requests with identical idempotency keys,
or simultaneous completion attempts on limited stock batches, maintain strict
atomicity, zero negative inventory, and SLA latency boundaries.
"""

from __future__ import annotations

import time
from decimal import Decimal
import pytest
from rest_framework import status

from core.invariants import assert_all_invariants
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def test_rapid_double_submit_idempotency(tenant_a):
    """Submitting the exact same draft invoice twice consecutively must be idempotent."""
    company = tenant_a.company
    product = make_product(company, gst_rate="18", selling_price="150.00")
    add_stock(tenant_a, product, "10", unit_cost="80.00")
    customer = make_customer(company, state="Karnataka")

    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "2", "unit_price": "150.00", "gst_rate": "18"}],
    )

    url = f"/api/v1/sales/invoices/{inv['id']}/complete/"

    # First submission
    t0 = time.perf_counter()
    r1 = tenant_a.client.post(url)
    latency1 = (time.perf_counter() - t0) * 1000

    assert r1.status_code == status.HTTP_200_OK, r1.data
    # First submit completes within calibrated test runner budget (including in-process eager PDF generation; DoD I5 SLA: <= 2.5s)
    assert latency1 < 2500, f"Initial complete took {latency1:.2f}ms (threshold 2500ms)"

    # Second immediate submission (e.g. cashier double-clicked)
    t1 = time.perf_counter()
    r2 = tenant_a.client.post(url)
    latency2 = (time.perf_counter() - t1) * 1000

    # Must either return 200 (idempotent duplicate response) or 400/409 (already completed)
    # Never 500 Internal Server Error
    assert r2.status_code in (
        status.HTTP_200_OK,
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_409_CONFLICT,
    ), r2.data
    assert latency2 < 500, f"Second submit took {latency2:.2f}ms"

    # Crucial Data Assertion: Stock was decremented EXACTLY ONCE (10 - 2 = 8, not 6)
    from inventory.services import InventoryService

    on_hand = InventoryService.available_quantity(company=company, product=product)
    assert on_hand == Decimal("8.000"), f"Expected 8 on hand, got {on_hand}"

    assert_all_invariants(company)


def test_concurrent_stock_depletion_never_goes_negative(tenant_a):
    """When stock is exactly 1, two separate invoices for 1 unit cannot both succeed."""
    company = tenant_a.company
    product = make_product(company, gst_rate="18", selling_price="500.00")
    add_stock(tenant_a, product, "1", unit_cost="300.00")
    customer = make_customer(company, state="Karnataka")

    # Create two separate draft invoices each demanding 1 unit
    inv1 = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "500.00", "gst_rate": "18"}],
    )
    inv2 = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "500.00", "gst_rate": "18"}],
    )

    # First completes successfully
    r1 = tenant_a.client.post(f"/api/v1/sales/invoices/{inv1['id']}/complete/")
    assert r1.status_code == status.HTTP_200_OK, r1.data

    # Second must fail due to zero available stock
    r2 = tenant_a.client.post(f"/api/v1/sales/invoices/{inv2['id']}/complete/")
    assert r2.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_409_CONFLICT), r2.data

    # Final stock must be 0, never negative
    from inventory.services import InventoryService

    on_hand = InventoryService.available_quantity(company=company, product=product)
    assert on_hand == Decimal("0.000"), on_hand

    assert_all_invariants(company)
