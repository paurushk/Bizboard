"""Ledger Service — dynamic statements, no stored ledger tables (E5.1)."""

from decimal import Decimal

import pytest
from django.apps import apps
from django.db import connection

from tests.conftest import (
    add_stock, create_draft_invoice, create_draft_purchase, make_customer, make_product, make_supplier,
)

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
    # B1-009: the running balance must foot customer_outstanding(), which
    # only nets *allocated* amounts -- an unallocated receipt is visible on
    # its own row (is_advance/unallocated) but must not move the balance.
    assert Decimal(str(entries[1]["balance"])) == Decimal("1180.00")
    assert entries[1]["is_advance"] is True
    assert Decimal(str(entries[1]["unallocated"])) == Decimal("500.00")


def test_customer_statement_foots_outstanding_end_to_end(tenant_a):
    """B1-009: the two surfaces must agree even with an unallocated advance."""
    from ledgers.services import LedgerService

    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "100")
    customer = make_customer(tenant_a.company, state="Karnataka")
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "10", "unit_price": "100"}
    ])
    tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    tenant_a.client.post("/api/v1/payments/receipts/", {
        "customer": customer.id, "amount": "500", "mode": "CASH",
    }, format="json")

    outstanding = LedgerService.customer_outstanding(tenant_a.company, customer)
    statement = LedgerService.customer_statement(tenant_a.company, customer)
    closing = statement[-1]["balance"] if statement else Decimal("0")
    assert outstanding == closing == Decimal("1180.00")


def test_supplier_statement_foots_outstanding_with_unallocated_payment(tenant_a):
    """B1-009 (AP side): same fix, mirrored for supplier payments."""
    from ledgers.services import LedgerService

    supplier = make_supplier(tenant_a.company)
    product = make_product(tenant_a.company, purchase_price="100", gst_rate="0")
    draft = create_draft_purchase(
        tenant_a, supplier, [{"product": product.id, "quantity": "5", "unit_price": "100"}],
    )
    resp = tenant_a.client.post(f"/api/v1/purchases/invoices/{draft['id']}/complete/")
    assert resp.status_code == 200, resp.data

    tenant_a.client.post("/api/v1/payments/supplier-payments/", {
        "supplier": supplier.id, "amount": "200", "mode": "CASH",
    }, format="json")

    outstanding = LedgerService.supplier_outstanding(tenant_a.company, supplier)
    statement = LedgerService.supplier_statement(tenant_a.company, supplier)
    closing = statement[-1]["balance"] if statement else Decimal("0")
    assert outstanding == closing == Decimal("500.00")

    payment_rows = [row for row in statement if row["type"] == "PAYMENT"]
    assert payment_rows and payment_rows[0]["is_advance"] is True
    assert Decimal(str(payment_rows[0]["unallocated"])) == Decimal("200.00")


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


def test_customer_endpoint_exposes_real_outstanding(tenant_a):
    """CustomerSerializer must carry a live outstanding, not 0 (masters/serializers.py)."""
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "100")
    customer = make_customer(tenant_a.company, state="Karnataka")
    other = make_customer(tenant_a.company, state="Karnataka")
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "10", "unit_price": "100"}
    ])
    tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")  # 1180

    detail = tenant_a.client.get(f"/api/v1/customers/{customer.id}/")
    assert Decimal(detail.data["outstanding"]) == Decimal("1180.00")

    listing = tenant_a.client.get("/api/v1/customers/")
    by_id = {row["id"]: row for row in listing.data["results"]}
    assert Decimal(by_id[customer.id]["outstanding"]) == Decimal("1180.00")
    assert Decimal(by_id[other.id]["outstanding"]) == Decimal("0")


def test_supplier_endpoint_exposes_real_outstanding(tenant_a):
    """SupplierSerializer must carry a live outstanding, not 0 (masters/serializers.py)."""
    supplier = make_supplier(tenant_a.company)
    other = make_supplier(tenant_a.company)
    product = make_product(tenant_a.company, purchase_price="100", gst_rate="0")
    draft = create_draft_purchase(
        tenant_a, supplier, [{"product": product.id, "quantity": "5", "unit_price": "100"}],
    )
    resp = tenant_a.client.post(f"/api/v1/purchases/invoices/{draft['id']}/complete/")
    assert resp.status_code == 200, resp.data

    detail = tenant_a.client.get(f"/api/v1/suppliers/{supplier.id}/")
    assert Decimal(detail.data["outstanding"]) == Decimal("500.00")

    listing = tenant_a.client.get("/api/v1/suppliers/")
    by_id = {row["id"]: row for row in listing.data["results"]}
    assert Decimal(by_id[supplier.id]["outstanding"]) == Decimal("500.00")
    assert Decimal(by_id[other.id]["outstanding"]) == Decimal("0")
