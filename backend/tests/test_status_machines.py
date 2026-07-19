"""Document status machines (§4) and completed-immutability (§5)."""

from decimal import Decimal

import pytest

from inventory.models import MovementType, StockMovement
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db


def _completed_invoice(tenant, product=None, customer=None, qty="2"):
    product = product or make_product(tenant.company)
    add_stock(tenant, product, "10")
    customer = customer or make_customer(tenant.company)
    inv = create_draft_invoice(tenant, customer, [
        {"product": product.id, "quantity": qty, "unit_price": "100"}
    ])
    resp = tenant.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 200, resp.data
    return resp.data, product, customer


def test_complete_assigns_number_and_status(tenant_a):
    data, _, _ = _completed_invoice(tenant_a)
    assert data["status"] == "COMPLETED"
    assert data["number"].startswith("INV-")


def test_cannot_complete_twice(tenant_a):
    data, _, _ = _completed_invoice(tenant_a)
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{data['id']}/complete/")
    assert resp.status_code == 400


def test_completed_invoice_cannot_be_edited(tenant_a):
    data, product, customer = _completed_invoice(tenant_a)
    resp = tenant_a.client.patch(f"/api/v1/sales/invoices/{data['id']}/", {
        "notes": "sneaky edit",
        "items": [{"product": product.id, "quantity": "1", "unit_price": "1"}],
    }, format="json")
    assert resp.status_code == 400


def test_completed_invoice_cannot_be_deleted(tenant_a):
    data, _, _ = _completed_invoice(tenant_a)
    resp = tenant_a.client.delete(f"/api/v1/sales/invoices/{data['id']}/")
    assert resp.status_code == 400


def test_draft_can_be_edited_and_deleted(tenant_a):
    product = make_product(tenant_a.company)
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "2", "unit_price": "100"}
    ])
    resp = tenant_a.client.patch(f"/api/v1/sales/invoices/{inv['id']}/", {
        "items": [{"product": product.id, "quantity": "5", "unit_price": "90"}],
    }, format="json")
    assert resp.status_code == 200
    assert Decimal(resp.data["items"][0]["quantity"]) == Decimal("5")

    resp = tenant_a.client.delete(f"/api/v1/sales/invoices/{inv['id']}/")
    assert resp.status_code == 204


def test_cancel_completed_sale_restores_stock(tenant_a):
    data, product, _ = _completed_invoice(tenant_a, qty="3")
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{data['id']}/cancel/")
    assert resp.status_code == 200
    assert resp.data["status"] == "CANCELLED"
    # SALE movement is untouched; an ADJUSTMENT reverses it
    assert StockMovement.objects.filter(movement_type=MovementType.SALE).count() == 1
    adj = StockMovement.objects.get(movement_type=MovementType.ADJUSTMENT)
    assert adj.quantity == Decimal("3")


def test_cannot_cancel_invoice_with_completed_return(tenant_a):
    data, product, customer = _completed_invoice(tenant_a, qty="3")
    ret = tenant_a.client.post("/api/v1/sales/returns/", {
        "customer": customer.id, "sales_invoice": data["id"],
        "items": [{"product": product.id, "quantity": "1", "unit_price": "100"}],
    }, format="json")
    tenant_a.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/")
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{data['id']}/cancel/")
    assert resp.status_code == 400


def test_fully_returned_invoice_marked_returned(tenant_a):
    data, product, customer = _completed_invoice(tenant_a, qty="2")
    ret = tenant_a.client.post("/api/v1/sales/returns/", {
        "customer": customer.id, "sales_invoice": data["id"],
        "items": [{"product": product.id, "quantity": "2", "unit_price": "100"}],
    }, format="json")
    resp = tenant_a.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/")
    assert resp.status_code == 200
    inv = tenant_a.client.get(f"/api/v1/sales/invoices/{data['id']}/")
    assert inv.data["status"] == "RETURNED"


def test_return_cannot_exceed_sold_quantity(tenant_a):
    data, product, customer = _completed_invoice(tenant_a, qty="2")
    ret = tenant_a.client.post("/api/v1/sales/returns/", {
        "customer": customer.id, "sales_invoice": data["id"],
        "items": [{"product": product.id, "quantity": "5", "unit_price": "100"}],
    }, format="json")
    resp = tenant_a.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/")
    assert resp.status_code == 400


def test_quotation_convert_preserves_lines(tenant_a):
    product = make_product(tenant_a.company)
    customer = make_customer(tenant_a.company)
    quote = tenant_a.client.post("/api/v1/sales/quotations/", {
        "customer": customer.id,
        "items": [{"product": product.id, "quantity": "4", "unit_price": "150"}],
    }, format="json")
    assert quote.status_code == 201, quote.data

    resp = tenant_a.client.post(f"/api/v1/sales/quotations/{quote.data['id']}/convert/")
    assert resp.status_code == 200
    assert resp.data["status"] == "DRAFT"
    assert Decimal(resp.data["items"][0]["quantity"]) == Decimal("4")

    q = tenant_a.client.get(f"/api/v1/sales/quotations/{quote.data['id']}/")
    assert q.data["status"] == "CONVERTED"
    assert q.data["converted_invoice"] == resp.data["id"]

    # Cannot convert twice
    resp = tenant_a.client.post(f"/api/v1/sales/quotations/{quote.data['id']}/convert/")
    assert resp.status_code == 400


def test_purchase_status_machine(tenant_a):
    product = make_product(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    pur = create_draft_purchase(tenant_a, supplier, [
        {"product": product.id, "quantity": "5", "unit_price": "80"}
    ])
    resp = tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/")
    assert resp.status_code == 200
    assert resp.data["number"].startswith("PUR-")

    # Completed purchase cannot be line-edited
    resp = tenant_a.client.patch(f"/api/v1/purchases/invoices/{pur['id']}/", {
        "items": [{"product": product.id, "quantity": "1", "unit_price": "1"}],
    }, format="json")
    assert resp.status_code == 400

    # Cancel reverses stock
    resp = tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/cancel/")
    assert resp.status_code == 200
    from inventory.models import StockBalance

    assert StockBalance.objects.get(product=product).on_hand == Decimal("0")
