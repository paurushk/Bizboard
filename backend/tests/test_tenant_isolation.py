"""Tenant isolation — every query scoped by company_id (§3.1.8, E7.5)."""

import pytest

from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db


def test_customers_are_isolated(tenant_a, tenant_b):
    make_customer(tenant_a.company, name="Alpha Customer")
    resp = tenant_b.client.get("/api/v1/customers/")
    assert resp.status_code == 200
    assert resp.data["count"] == 0


def test_cannot_retrieve_other_companys_invoice(tenant_a, tenant_b):
    product = make_product(tenant_a.company)
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100"}
    ])
    resp = tenant_b.client.get(f"/api/v1/sales/invoices/{inv['id']}/")
    assert resp.status_code == 404


def test_cannot_use_other_companys_product_or_customer(tenant_a, tenant_b):
    product_a = make_product(tenant_a.company)
    customer_b = make_customer(tenant_b.company)
    resp = tenant_b.client.post("/api/v1/sales/invoices/", {
        "customer": customer_b.id,
        "items": [{"product": product_a.id, "quantity": "1", "unit_price": "100"}],
    }, format="json")
    assert resp.status_code == 400

    customer_a = make_customer(tenant_a.company)
    product_b = make_product(tenant_b.company)
    resp = tenant_b.client.post("/api/v1/sales/invoices/", {
        "customer": customer_a.id,
        "items": [{"product": product_b.id, "quantity": "1", "unit_price": "100"}],
    }, format="json")
    assert resp.status_code == 400


def test_stock_balances_are_isolated(tenant_a, tenant_b):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    resp = tenant_b.client.get("/api/v1/inventory/balances/")
    assert resp.data["count"] == 0


def test_ledger_access_is_isolated(tenant_a, tenant_b):
    customer = make_customer(tenant_a.company)
    resp = tenant_b.client.get(f"/api/v1/ledgers/customers/{customer.id}/")
    assert resp.status_code == 404


def test_document_numbers_are_per_company(tenant_a, tenant_b):
    for tenant in (tenant_a, tenant_b):
        product = make_product(tenant.company)
        add_stock(tenant, product, "10")
        customer = make_customer(tenant.company)
        inv = create_draft_invoice(tenant, customer, [
            {"product": product.id, "quantity": "1", "unit_price": "100"}
        ])
        resp = tenant.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
        # Both companies get INV-00001 — sequences are independent
        assert resp.data["number"] == "INV-00001"


def test_search_is_isolated(tenant_a, tenant_b):
    make_customer(tenant_a.company, name="UniqueAlphaName")
    resp = tenant_b.client.get("/api/v1/search/", {"q": "UniqueAlphaName"})
    assert resp.data["customers"] == []


def test_unauthenticated_requests_rejected():
    from rest_framework.test import APIClient

    resp = APIClient().get("/api/v1/customers/")
    assert resp.status_code == 401


def test_receipt_for_other_companys_customer_rejected(tenant_a, tenant_b):
    customer_a = make_customer(tenant_a.company)
    resp = tenant_b.client.post("/api/v1/payments/receipts/", {
        "customer": customer_a.id, "amount": "100", "mode": "CASH",
    }, format="json")
    assert resp.status_code == 400


def test_cross_tenant_write_attempts_all_rejected(tenant_a, tenant_b):
    """BUG-721 — every mutating endpoint (PATCH/DELETE/action) must reject a
    request scoped to another tenant's object id with 404, not just GET/create.
    IDs are sequential BigAutoFields across the whole system, so this is a
    realistic, cheap cross-tenant attack surface to leave untested."""
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    invoice = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100"}
    ])
    purchase = create_draft_purchase(tenant_a, supplier, [
        {"product": product.id, "quantity": "1", "unit_price": "80"}
    ])

    cases = [
        ("patch", f"/api/v1/sales/invoices/{invoice['id']}/", {"invoice_discount": "5"}),
        ("post", f"/api/v1/sales/invoices/{invoice['id']}/complete/", None),
        ("post", f"/api/v1/sales/invoices/{invoice['id']}/cancel/", None),
        ("post", f"/api/v1/sales/invoices/{invoice['id']}/regenerate-pdf/", None),
        ("post", f"/api/v1/sales/invoices/{invoice['id']}/share/", {"channel": "email"}),
        ("patch", f"/api/v1/purchases/invoices/{purchase['id']}/", {"invoice_discount": "5"}),
        ("post", f"/api/v1/purchases/invoices/{purchase['id']}/complete/", None),
        ("post", f"/api/v1/purchases/invoices/{purchase['id']}/cancel/", None),
        ("patch", f"/api/v1/customers/{customer.id}/", {"name": "Hijacked"}),
        ("delete", f"/api/v1/customers/{customer.id}/", None),
        ("patch", f"/api/v1/suppliers/{supplier.id}/", {"name": "Hijacked"}),
        ("delete", f"/api/v1/suppliers/{supplier.id}/", None),
        ("patch", f"/api/v1/products/{product.id}/", {"name": "Hijacked"}),
        ("delete", f"/api/v1/products/{product.id}/", None),
    ]
    for method, path, payload in cases:
        call = getattr(tenant_b.client, method)
        resp = call(path, payload, format="json") if payload is not None else call(path)
        assert resp.status_code == 404, f"{method.upper()} {path} returned {resp.status_code}, expected 404"
