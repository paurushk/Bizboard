"""A fully-returned invoice must not still look like an active sale, and a
partial return must be visible without losing COMPLETED status.

Covers the return_state (NONE/PARTIAL/FULL) field added to
SalesInvoiceSerializer, and the sales_invoice filter on /sales/returns/.
"""

import pytest

from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _complete_return(tenant, customer, invoice_id, product, quantity, unit_price="50"):
    created = tenant.client.post(
        "/api/v1/sales/returns/",
        {
            "customer": customer.id,
            "sales_invoice": invoice_id,
            "items": [{"product": product.id, "quantity": quantity, "unit_price": unit_price}],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    complete = tenant.client.post(f"/api/v1/sales/returns/{created.data['id']}/complete/")
    assert complete.status_code == 200, complete.data
    return complete.data


def test_partial_return_keeps_completed_status_but_flags_return_state(tenant_a):
    product = make_product(tenant_a.company, sku="RSV-1")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "10", "unit_price": "50"}]
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200

    _complete_return(tenant_a, customer, inv["id"], product, "3")

    detail = tenant_a.client.get(f"/api/v1/sales/invoices/{inv['id']}/")
    assert detail.status_code == 200
    assert detail.data["status"] == "COMPLETED"
    assert detail.data["return_state"] == "PARTIAL"

    listing = tenant_a.client.get("/api/v1/sales/invoices/")
    assert listing.status_code == 200
    row = next(r for r in listing.data["results"] if r["id"] == inv["id"])
    assert row["status"] == "COMPLETED"
    assert row["return_state"] == "PARTIAL"

    linked = tenant_a.client.get(f"/api/v1/sales/returns/?sales_invoice={inv['id']}")
    assert linked.status_code == 200
    assert len(linked.data["results"]) == 1


def test_multiple_partial_returns_against_one_invoice(tenant_a):
    product = make_product(tenant_a.company, sku="RSV-MULTI")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "10", "unit_price": "50"}]
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    _complete_return(tenant_a, customer, inv["id"], product, "3")
    _complete_return(tenant_a, customer, inv["id"], product, "2")
    detail = tenant_a.client.get(f"/api/v1/sales/invoices/{inv['id']}/")
    assert detail.status_code == 200
    assert detail.data["status"] == "COMPLETED"
    assert detail.data["return_state"] == "PARTIAL"
    linked = tenant_a.client.get(f"/api/v1/sales/returns/?sales_invoice={inv['id']}")
    assert linked.status_code == 200
    assert len(linked.data["results"]) == 2


def test_full_return_flips_status_and_return_state(tenant_a):
    product = make_product(tenant_a.company, sku="RSV-2")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "5", "unit_price": "50"}]
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200

    _complete_return(tenant_a, customer, inv["id"], product, "5")

    detail = tenant_a.client.get(f"/api/v1/sales/invoices/{inv['id']}/")
    assert detail.status_code == 200
    assert detail.data["status"] == "RETURNED"
    assert detail.data["return_state"] == "FULL"

    listing = tenant_a.client.get("/api/v1/sales/invoices/")
    row = next(r for r in listing.data["results"] if r["id"] == inv["id"])
    assert row["status"] == "RETURNED"
    assert row["return_state"] == "FULL"


def test_no_return_leaves_return_state_none(tenant_a):
    product = make_product(tenant_a.company, sku="RSV-3")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "5", "unit_price": "50"}]
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200

    detail = tenant_a.client.get(f"/api/v1/sales/invoices/{inv['id']}/")
    assert detail.data["status"] == "COMPLETED"
    assert detail.data["return_state"] == "NONE"
