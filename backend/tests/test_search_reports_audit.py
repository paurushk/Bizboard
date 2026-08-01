"""Search Service, Report Service registers, exports and audit log."""

from decimal import Decimal

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


def _setup_documents(tenant):
    product = make_product(tenant.company, name="Blue Pen", sku="PEN-B", barcode="890123")
    add_stock(tenant, product, "100")
    customer = make_customer(tenant.company, name="Sharma Stores", state="Karnataka")
    supplier = make_supplier(tenant.company, name="Pen Wholesale")
    inv = create_draft_invoice(tenant, customer, [
        {"product": product.id, "quantity": "10", "unit_price": "100"}
    ])
    tenant.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    pur = create_draft_purchase(tenant, supplier, [
        {"product": product.id, "quantity": "20", "unit_price": "80"}
    ])
    tenant.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/")
    return product, customer, supplier


def test_universal_search_by_name_sku_barcode_and_number(tenant_a):
    product, customer, supplier = _setup_documents(tenant_a)

    resp = tenant_a.client.get("/api/v1/search/", {"q": "Sharma"})
    assert len(resp.data["customers"]) == 1

    resp = tenant_a.client.get("/api/v1/search/", {"q": "PEN-B"})
    assert len(resp.data["products"]) == 1

    resp = tenant_a.client.get("/api/v1/search/", {"q": "890123"})
    assert len(resp.data["products"]) == 1

    resp = tenant_a.client.get("/api/v1/search/", {"q": "INV-00001"})
    assert len(resp.data["invoices"]) == 1
    assert resp.data["invoices"][0]["kind"] == "sales"


def test_sales_and_purchase_registers(tenant_a):
    _setup_documents(tenant_a)
    resp = tenant_a.client.get("/api/v1/reports/sales-register/")
    assert len(resp.data["rows"]) == 1
    assert Decimal(str(resp.data["totals"]["grand_total"])) == Decimal("1180.00")

    resp = tenant_a.client.get("/api/v1/reports/purchase-register/")
    assert len(resp.data["rows"]) == 1
    assert Decimal(str(resp.data["totals"]["grand_total"])) == Decimal("1888.00")


def test_sales_register_date_range_filters_across_month_boundary(tenant_a):
    """BUG-727 — GSTR-1 style monthly extraction depends on invoice_date
    boundaries being inclusive/exclusive exactly at the edges."""
    product = make_product(tenant_a.company, name="Blue Pen", sku="PEN-B")
    add_stock(tenant_a, product, "100")
    customer = make_customer(tenant_a.company, name="Sharma Stores", state="Karnataka")

    def _invoice_on(date_str):
        payload = {
            "customer": customer.id,
            "invoice_type": "GST",
            "invoice_date": date_str,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100"}],
        }
        resp = tenant_a.client.post("/api/v1/sales/invoices/", payload, format="json")
        assert resp.status_code == 201, resp.data
        complete = tenant_a.client.post(f"/api/v1/sales/invoices/{resp.data['id']}/complete/")
        assert complete.status_code == 200
        return complete.data

    june_30 = _invoice_on("2026-06-30")
    july_1 = _invoice_on("2026-07-01")
    july_31 = _invoice_on("2026-07-31")
    aug_1 = _invoice_on("2026-08-01")

    resp = tenant_a.client.get("/api/v1/reports/sales-register/", {
        "date_from": "2026-07-01", "date_to": "2026-07-31",
    })
    numbers = {row["number"] for row in resp.data["rows"]}
    assert numbers == {july_1["number"], july_31["number"]}
    assert june_30["number"] not in numbers
    assert aug_1["number"] not in numbers


def test_inventory_summary_and_product_sales(tenant_a):
    _setup_documents(tenant_a)
    resp = tenant_a.client.get("/api/v1/reports/inventory-summary/")
    assert Decimal(str(resp.data["rows"][0]["on_hand"])) == Decimal("110")  # 100 + 20 − 10

    resp = tenant_a.client.get("/api/v1/reports/product-sales/")
    assert Decimal(str(resp.data["rows"][0]["quantity"])) == Decimal("10")


def test_csv_export(tenant_a):
    _setup_documents(tenant_a)
    resp = tenant_a.client.get("/api/v1/exports/sales-register/")
    assert resp.status_code == 200
    assert resp["Content-Type"] == "text/csv"
    assert b"INV-00001" in resp.content


def test_csv_export_requires_can_export(tenant_a):
    """P0-313 / BUG-612: staff without can_export must be denied at the API."""
    _setup_documents(tenant_a)
    resp = tenant_a.staff_client.get("/api/v1/exports/sales-register/")
    assert resp.status_code == 403


def test_audit_log_records_and_is_owner_only(tenant_a):
    _setup_documents(tenant_a)
    resp = tenant_a.client.get("/api/v1/audit/")
    assert resp.status_code == 200
    actions = {row["action"] for row in resp.data["results"]}
    assert "CREATE" in actions

    resp = tenant_a.staff_client.get("/api/v1/audit/")
    assert resp.status_code == 403


def test_openapi_schema_available(tenant_a):
    from django.conf import settings

    if not settings.ENABLE_API_DOCS:
        # Docs may be disabled in locked-down deploys.
        resp = tenant_a.client.get("/api/v1/schema/")
        assert resp.status_code == 404
        return
    resp = tenant_a.client.get("/api/v1/schema/")
    assert resp.status_code == 200
