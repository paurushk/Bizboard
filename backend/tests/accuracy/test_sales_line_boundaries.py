"""TC-EXP-003: Accuracy & Negative Boundary Validation on Sales Invoice Lines.

Validates that invalid quantities, negative prices, and malformed line items
are strictly rejected at the serializer boundary before any state mutation occurs,
leaving database tables and invariants untouched.
"""

from __future__ import annotations

import time
from decimal import Decimal
import pytest
from rest_framework import status

from core.invariants import assert_all_invariants
from tests.conftest import add_stock, make_customer, make_product

pytestmark = pytest.mark.django_db


def test_sales_invoice_rejects_negative_unit_price(tenant_a):
    """Negative unit prices must be rejected with 400 and cause no DB mutation."""
    company = tenant_a.company
    product = make_product(company, gst_rate="18", selling_price="100.00")
    add_stock(tenant_a, product, "10", unit_cost="50.00")
    customer = make_customer(company, state="Karnataka")

    payload = {
        "customer": customer.id,
        "invoice_date": "2026-09-26",
        "items": [
            {
                "product": product.id,
                "quantity": "2",
                "unit_price": "-100.00",
                "gst_rate": "18",
            }
        ],
    }

    # Warm up serializer and view route
    tenant_a.client.get("/api/v1/sales/invoices/")

    t0 = time.perf_counter()
    resp = tenant_a.client.post("/api/v1/sales/invoices/", payload, format="json")
    latency_ms = (time.perf_counter() - t0) * 1000

    # Must reject with 400 Bad Request
    assert resp.status_code == status.HTTP_400_BAD_REQUEST, resp.data
    # Performance assertion: validation rejection must be fast (SLA: <= 500ms on dev)
    assert latency_ms < 500, f"Validation latency was {latency_ms:.2f}ms"

    # Verify no invoice was created
    from sales.models import SalesInvoice

    assert not SalesInvoice.objects.filter(company=company, customer=customer).exists()

    # Invariants must remain strictly valid
    assert_all_invariants(company)


def test_sales_invoice_rejects_zero_quantity(tenant_a):
    """Zero quantity line item must be rejected."""
    company = tenant_a.company
    product = make_product(company, gst_rate="18", selling_price="100.00")
    customer = make_customer(company, state="Karnataka")

    payload = {
        "customer": customer.id,
        "invoice_date": "2026-09-26",
        "items": [
            {
                "product": product.id,
                "quantity": "0",
                "unit_price": "100.00",
                "gst_rate": "18",
            }
        ],
    }

    resp = tenant_a.client.post("/api/v1/sales/invoices/", payload, format="json")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST, resp.data
    assert_all_invariants(company)


def test_sales_invoice_rejects_out_of_stock_completion(tenant_a):
    """Completing an invoice demanding more stock than available must fail cleanly."""
    company = tenant_a.company
    product = make_product(company, gst_rate="18", selling_price="100.00")
    add_stock(tenant_a, product, "5", unit_cost="50.00")
    customer = make_customer(company, state="Karnataka")

    # Create draft for 10 units when only 5 units exist
    from tests.conftest import create_draft_invoice

    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "10", "unit_price": "100.00", "gst_rate": "18"}],
    )

    # Attempting to complete must fail
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_409_CONFLICT), done.data

    # Stock must remain untouched at 5 units
    from inventory.services import InventoryService

    on_hand = InventoryService.available_quantity(company=company, product=product)
    assert on_hand == Decimal("5.000"), on_hand

    assert_all_invariants(company)


def test_complete_failure_then_retry_posts_stock_once(tenant_a):
    """Complete is rejected while stock is short. After stock is added, one retry posts once."""
    from inventory.services import InventoryService
    from tests.conftest import create_draft_invoice

    company = tenant_a.company
    product = make_product(company, gst_rate="18", selling_price="100.00")
    add_stock(tenant_a, product, "1", unit_cost="50.00")
    customer = make_customer(company, state="Karnataka")
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "5", "unit_price": "100.00", "gst_rate": "18"}],
    )
    blocked = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert blocked.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_409_CONFLICT), blocked.data
    assert InventoryService.available_quantity(company=company, product=product) == Decimal("1.000")

    from inventory.models import MovementType

    InventoryService.post_movement(
        company=company, product=product, movement_type=MovementType.PURCHASE,
        quantity=Decimal("4"), unit_cost=Decimal("50.00"), user=tenant_a.owner,
    )
    ok = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert ok.status_code == status.HTTP_200_OK, ok.data
    again = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert again.status_code in (
        status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST, status.HTTP_409_CONFLICT,
    )
    assert InventoryService.available_quantity(company=company, product=product) == Decimal("0.000")
    assert_all_invariants(company)
