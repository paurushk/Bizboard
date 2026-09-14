"""A product's base unit can change once stock is zero (see
test_reported_item_ux.py), but open documents that haven't posted stock yet
still carry a quantity keyed to the OLD unit -- they'd be silently resolved
against the new unit whenever they're eventually completed. These tests
cover the extra guard in `assert_no_open_documents_for_unit_change`."""

from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from masters.models import Product
from tests.conftest import add_stock, make_customer, make_product, make_supplier

pytestmark = pytest.mark.django_db


def _upload_products(tenant, content: bytes):
    return tenant.client.post("/api/v1/imports/", {
        "kind": "PRODUCTS",
        "file": SimpleUploadedFile("items.csv", content, content_type="text/csv"),
    }, format="multipart")


def _zero_stock_product(tenant_a, sku):
    from inventory.models import MovementType
    from inventory.services import InventoryService

    resp = tenant_a.client.post(
        "/api/v1/products/",
        {"name": f"Item {sku}", "sku": sku, "gst_rate": "18", "unit_name": "PCS"},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    product = Product.objects.get(pk=resp.data["id"])
    add_stock(tenant_a, product, "5")
    InventoryService.post_movement(
        company=tenant_a.company, product=product,
        movement_type=MovementType.ADJUSTMENT,
        quantity=Decimal("-5"), reason="zero out for unit change", user=tenant_a.owner,
    )
    return product


def _change_unit(tenant_a, product):
    return tenant_a.client.patch(
        f"/api/v1/products/{product.id}/", {"unit_name": "KG"}, format="json",
    )


def test_unit_change_blocked_by_draft_quotation(tenant_a):
    product = _zero_stock_product(tenant_a, "OPEN-QTN")
    customer = make_customer(tenant_a.company)
    quote = tenant_a.client.post(
        "/api/v1/sales/quotations/",
        {"customer": customer.id, "items": [{"product": product.id, "quantity": "4", "unit_price": "150"}]},
        format="json",
    )
    assert quote.status_code == 201, quote.data

    resp = _change_unit(tenant_a, product)
    assert resp.status_code == 400, resp.data
    assert "quotation" in str(resp.data).lower()

    cancel = tenant_a.client.post(f"/api/v1/sales/quotations/{quote.data['id']}/cancel/")
    assert cancel.status_code == 200, cancel.data
    resp = _change_unit(tenant_a, product)
    assert resp.status_code == 200, resp.data


def test_unit_change_blocked_by_confirmed_sales_order(tenant_a):
    """A confirmed SO already bumps StockBalance.reserved (caught by the
    existing zero-stock check), but a maintenance rebuild_balance() recompute
    re-clamps reserved to on_hand and would silently zero it out again -- the
    open-documents check is the check that reliably survives that. Assert the
    block here without depending on which of the two guards caught it."""
    product = _zero_stock_product(tenant_a, "OPEN-SO")
    tenant_a.company.negative_stock_policy = "WARN"
    tenant_a.company.save()
    customer = make_customer(tenant_a.company)
    order = tenant_a.client.post(
        "/api/v1/sales/orders/",
        {"customer": customer.id, "items": [{"product": product.id, "quantity": "4", "unit_price": "150"}]},
        format="json",
    )
    assert order.status_code == 201, order.data
    confirmed = tenant_a.client.post(f"/api/v1/sales/orders/{order.data['id']}/confirm/")
    assert confirmed.status_code == 200, confirmed.data

    resp = _change_unit(tenant_a, product)
    assert resp.status_code == 400, resp.data

    cancelled = tenant_a.client.post(f"/api/v1/sales/orders/{order.data['id']}/cancel/")
    assert cancelled.status_code == 200, cancelled.data
    resp = _change_unit(tenant_a, product)
    assert resp.status_code == 200, resp.data


def test_unit_change_blocked_by_confirmed_sales_order_with_reserved_reclamped_to_zero(tenant_a):
    """Isolate the open-documents check from the zero-stock check: force
    StockBalance.reserved back to 0 via the same rebuild_balance() recompute
    a maintenance/reconcile action would run, so only the open-documents
    check is left standing between a confirmed SO and a silent unit change."""
    from inventory.models import StockBalance
    from inventory.services import InventoryService

    product = _zero_stock_product(tenant_a, "OPEN-SO-2")
    tenant_a.company.negative_stock_policy = "WARN"
    tenant_a.company.save()
    customer = make_customer(tenant_a.company)
    order = tenant_a.client.post(
        "/api/v1/sales/orders/",
        {"customer": customer.id, "items": [{"product": product.id, "quantity": "4", "unit_price": "150"}]},
        format="json",
    )
    assert order.status_code == 201, order.data
    confirmed = tenant_a.client.post(f"/api/v1/sales/orders/{order.data['id']}/confirm/")
    assert confirmed.status_code == 200, confirmed.data
    assert StockBalance.objects.get(company=tenant_a.company, product=product).reserved == Decimal("4")

    warehouse = InventoryService.default_warehouse(tenant_a.company)
    InventoryService.rebuild_balance(tenant_a.company, product, warehouse)
    balance = StockBalance.objects.get(company=tenant_a.company, product=product, warehouse=warehouse)
    assert balance.on_hand == Decimal("0")
    assert balance.reserved == Decimal("0")

    resp = _change_unit(tenant_a, product)
    assert resp.status_code == 400, resp.data
    assert "sales order" in str(resp.data).lower()


def test_unit_change_blocked_by_open_purchase_order(tenant_a):
    product = _zero_stock_product(tenant_a, "OPEN-PO")
    supplier = make_supplier(tenant_a.company)
    po = tenant_a.client.post(
        "/api/v1/purchases/orders/",
        {
            "supplier": supplier.id,
            "purchase_type": "NON_GST",
            "items": [{"product": product.id, "quantity": "2", "unit_price": "100", "gst_rate": "0"}],
        },
        format="json",
    )
    assert po.status_code == 201, po.data

    resp = _change_unit(tenant_a, product)
    assert resp.status_code == 400, resp.data
    assert "purchase order" in str(resp.data).lower()

    cancel = tenant_a.client.post(f"/api/v1/purchases/orders/{po.data['id']}/cancel/")
    assert cancel.status_code == 200, cancel.data
    resp = _change_unit(tenant_a, product)
    assert resp.status_code == 200, resp.data


def test_unit_change_blocked_by_draft_sales_invoice(tenant_a):
    product = _zero_stock_product(tenant_a, "OPEN-INV")
    customer = make_customer(tenant_a.company)
    inv = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {"customer": customer.id, "items": [{"product": product.id, "quantity": "1", "unit_price": "150"}]},
        format="json",
    )
    assert inv.status_code == 201, inv.data

    resp = _change_unit(tenant_a, product)
    assert resp.status_code == 400, resp.data
    assert "invoice" in str(resp.data).lower()

    void = tenant_a.client.delete(f"/api/v1/sales/invoices/{inv.data['id']}/")
    assert void.status_code in (200, 204), void.data
    resp = _change_unit(tenant_a, product)
    assert resp.status_code == 200, resp.data


def test_csv_import_blocks_unit_change_with_stock_on_hand(tenant_a):
    """_commit_products writes `unit` via bulk_update(), bypassing
    ProductSerializer.validate() entirely -- the CSV import path needs its
    own copy of the same guard (imports/services.py _validate_row)."""
    product = make_product(tenant_a.company, sku="IMPORT-UNIT-1")
    product.unit = None
    from masters.models import Unit

    pcs, _ = Unit.objects.get_or_create(
        company=tenant_a.company, short_name="PCS", defaults={"name": "PCS", "uqc_code": "PCS"},
    )
    product.unit = pcs
    product.save(update_fields=["unit"])
    add_stock(tenant_a, product, "5")

    csv_content = b"name,sku,unit\nImport Unit 1,IMPORT-UNIT-1,KG\n"
    job = _upload_products(tenant_a, csv_content).data
    assert job["error_rows"] == 1, job
    assert "unit" in str(job["errors"]).lower()

    commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert commit.status_code == 400, commit.data
    product.refresh_from_db()
    assert product.unit_id == pcs.id


def test_csv_import_allows_unit_change_once_stock_is_zero(tenant_a):
    product = make_product(tenant_a.company, sku="IMPORT-UNIT-2")
    from masters.models import Unit

    pcs, _ = Unit.objects.get_or_create(
        company=tenant_a.company, short_name="PCS", defaults={"name": "PCS", "uqc_code": "PCS"},
    )
    product.unit = pcs
    product.save(update_fields=["unit"])

    csv_content = b"name,sku,unit\nImport Unit 2,IMPORT-UNIT-2,KG\n"
    job = _upload_products(tenant_a, csv_content).data
    assert job["error_rows"] == 0, job

    commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert commit.status_code == 200, commit.data
    product.refresh_from_db()
    assert (product.unit.short_name or "").upper() == "KG"
