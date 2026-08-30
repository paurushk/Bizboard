"""Ledger Service — dynamic statements, no stored ledger tables (E5.1)."""

from decimal import Decimal

import pytest
from django.apps import apps
from django.db import connection

from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def test_no_ledger_tables_exist():
    """MVP release DoD: no customer_ledgers / supplier_ledgers tables (§20)."""
    for model in apps.get_models():
        t = model._meta.db_table.lower()
        assert "customer_ledger" not in t and "supplier_ledger" not in t
    table_names = connection.introspection.table_names()
    assert not any("customer_ledger" in t.lower() or "supplier_ledger" in t.lower() for t in table_names)


def test_customer_statement_running_balance(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "100")
    customer = make_customer(tenant_a.company, state="Karnataka")

    # Invoice 1: 10 × 100 @18% = 1180
    inv1 = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "10", "unit_price": "100"}
    ])
    tenant_a.client.post(f"/api/v1/sales/invoices/{inv1['id']}/complete/")

    # Receipt of 500 (unallocated — still shows in statement)
    tenant_a.client.post("/api/v1/payments/receipts/", {
        "customer": customer.id, "amount": "500", "mode": "CASH",
    }, format="json")

    resp = tenant_a.client.get(f"/api/v1/ledgers/customers/{customer.id}/")
    entries = resp.data["entries"]
    assert [e["type"] for e in entries] == ["SALES_INVOICE", "RECEIPT"]
    assert Decimal(str(entries[0]["balance"])) == Decimal("1180.00")
    assert Decimal(str(entries[1]["balance"])) == Decimal("680.00")


def test_outstanding_uses_allocations_not_raw_receipts(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "100")
    customer = make_customer(tenant_a.company, state="Karnataka")
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "10", "unit_price": "100"}
    ])
    tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")  # 1180

    receipt = tenant_a.client.post("/api/v1/payments/receipts/", {
        "customer": customer.id, "amount": "500", "mode": "CASH",
    }, format="json")

    # Unallocated receipt: outstanding derived from allocations = full 1180 (§5.4)
    resp = tenant_a.client.get(f"/api/v1/ledgers/customers/{customer.id}/")
    assert Decimal(resp.data["outstanding"]) == Decimal("1180.00")

    tenant_a.client.post("/api/v1/payments/allocations/", {
        "receipt": receipt.data["id"], "sales_invoice": inv["id"], "amount": "500",
    }, format="json")
    resp = tenant_a.client.get(f"/api/v1/ledgers/customers/{customer.id}/")
    assert Decimal(resp.data["outstanding"]) == Decimal("680.00")


def test_sales_return_reduces_outstanding(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "100")
    customer = make_customer(tenant_a.company, state="Karnataka")
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "10", "unit_price": "100"}
    ])
    tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")  # 1180

    ret = tenant_a.client.post("/api/v1/sales/returns/", {
        "customer": customer.id, "sales_invoice": inv["id"],
        "items": [{"product": product.id, "quantity": "2", "unit_price": "100"}],
    }, format="json")
    tenant_a.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/")  # 236

    resp = tenant_a.client.get(f"/api/v1/ledgers/customers/{customer.id}/")
    assert Decimal(resp.data["outstanding"]) == Decimal("944.00")


def test_cancelled_invoice_excluded_from_ledger(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "100")
    customer = make_customer(tenant_a.company, state="Karnataka")
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "10", "unit_price": "100"}
    ])
    tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/cancel/")

    resp = tenant_a.client.get(f"/api/v1/ledgers/customers/{customer.id}/")
    assert Decimal(resp.data["outstanding"]) == Decimal("0.00")
    assert resp.data["entries"] == []


def test_dashboard_kpis_match_documents(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "100")
    customer = make_customer(tenant_a.company, state="Karnataka")
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "10", "unit_price": "100"}
    ])
    tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")

    resp = tenant_a.client.get("/api/v1/dashboard/")
    assert resp.status_code == 200
    assert Decimal(str(resp.data["sales_today"]["total"])) == Decimal("1180.00")
    assert resp.data["sales_today"]["count"] == 1
    assert Decimal(str(resp.data["receivables"])) == Decimal("1180.00")
