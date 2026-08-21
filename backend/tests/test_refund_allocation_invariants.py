"""Refund/allocation invariants — BB-000493/507 (pytest; hypothesis not in requirements)."""

from decimal import Decimal

import pytest

from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("alloc_amount,expect_status", [
    ("500.00", 201),
    ("1000.00", 201),
    ("1500.00", 400),
])
def test_allocation_respects_receipt_and_invoice_caps(tenant_a, alloc_amount, expect_status):
    """Allocations cannot exceed receipt balance or invoice outstanding."""
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "100")
    customer = make_customer(tenant_a.company, state="Karnataka")
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "10", "unit_price": "100"},
    ])
    tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    receipt = tenant_a.client.post("/api/v1/payments/receipts/", {
        "customer": customer.id,
        "amount": "2000",
        "mode": "UPI",
    }, format="json").data

    resp = tenant_a.client.post("/api/v1/payments/allocations/", {
        "receipt": receipt["id"],
        "sales_invoice": inv["id"],
        "amount": alloc_amount,
    }, format="json")
    assert resp.status_code == expect_status, resp.data

    if expect_status == 201:
        ledger = tenant_a.client.get(f"/api/v1/ledgers/customers/{customer.id}/")
        assert Decimal(ledger.data["outstanding"]) >= Decimal("0")
        assert Decimal(alloc_amount) <= Decimal("2000")
