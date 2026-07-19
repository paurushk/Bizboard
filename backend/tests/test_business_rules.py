"""Locked business rules (§5) — blocked customer, inactive product, stock policy."""

from decimal import Decimal

import pytest

from masters.models import Customer, Product
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def test_blocked_customer_cannot_be_invoiced(tenant_a):
    product = make_product(tenant_a.company)
    customer = make_customer(tenant_a.company, status=Customer.Status.BLOCKED)
    resp = tenant_a.client.post("/api/v1/sales/invoices/", {
        "customer": customer.id,
        "items": [{"product": product.id, "quantity": "1", "unit_price": "100"}],
    }, format="json")
    assert resp.status_code == 400


def test_customer_blocked_after_draft_cannot_complete(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100"}
    ])
    customer.status = Customer.Status.BLOCKED
    customer.save()
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 400


def test_inactive_product_cannot_be_sold(tenant_a):
    product = make_product(tenant_a.company, status=Product.Status.INACTIVE)
    customer = make_customer(tenant_a.company)
    resp = tenant_a.client.post("/api/v1/sales/invoices/", {
        "customer": customer.id,
        "items": [{"product": product.id, "quantity": "1", "unit_price": "100"}],
    }, format="json")
    assert resp.status_code == 400


def test_zero_quantity_rejected(tenant_a):
    product = make_product(tenant_a.company)
    customer = make_customer(tenant_a.company)
    resp = tenant_a.client.post("/api/v1/sales/invoices/", {
        "customer": customer.id,
        "items": [{"product": product.id, "quantity": "0", "unit_price": "100"}],
    }, format="json")
    assert resp.status_code == 400


def test_negative_stock_blocked_by_policy(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "1")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "5", "unit_price": "100"}
    ])
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 400
    # No stock movement was posted — atomic rollback
    from inventory.models import MovementType, StockMovement

    assert not StockMovement.objects.filter(movement_type=MovementType.SALE).exists()


def test_negative_stock_warn_policy_allows_sale(tenant_a):
    tenant_a.company.negative_stock_policy = "WARN"
    tenant_a.company.save()
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "1")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "5", "unit_price": "100"}
    ])
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 200
    assert resp.data["warnings"]
    from inventory.models import StockBalance

    assert StockBalance.objects.get(product=product).on_hand == Decimal("-4")


def test_purchase_requires_supplier(tenant_a):
    product = make_product(tenant_a.company)
    resp = tenant_a.client.post("/api/v1/purchases/invoices/", {
        "items": [{"product": product.id, "quantity": "1", "unit_price": "80"}],
    }, format="json")
    assert resp.status_code == 400


def test_referenced_product_soft_deletes(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "5")
    resp = tenant_a.client.delete(f"/api/v1/products/{product.id}/")
    assert resp.status_code == 200
    product.refresh_from_db()
    assert product.status == Product.Status.INACTIVE

    unused = make_product(tenant_a.company, sku="UNUSED-1")
    resp = tenant_a.client.delete(f"/api/v1/products/{unused.id}/")
    assert resp.status_code == 204


def test_invalid_hsn_rejected(tenant_a):
    resp = tenant_a.client.post("/api/v1/products/", {
        "name": "Bad HSN", "sku": "BH-1", "hsn_code": "12", "gst_rate": "18",
    }, format="json")
    assert resp.status_code == 400


def test_invalid_gst_rate_rejected(tenant_a):
    resp = tenant_a.client.post("/api/v1/products/", {
        "name": "Bad Rate", "sku": "BR-1", "gst_rate": "17",
    }, format="json")
    assert resp.status_code == 400
