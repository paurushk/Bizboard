"""Fixes for shop-floor item / stock / valuation reports."""

from decimal import Decimal

import pytest

from inventory.models import BatchLot, MovementType, StockMovement
from masters.hsn_catalog import search_hsn
from masters.models import Product
from tests.conftest import add_stock, make_product

pytestmark = pytest.mark.django_db


def test_product_sku_required(tenant_a):
    resp = tenant_a.client.post("/api/v1/products/", {"name": "No Code", "gst_rate": "18"}, format="json")
    assert resp.status_code == 400
    assert "sku" in resp.data or "item code" in str(resp.data).lower()


def test_product_accepts_category_and_brand_names(tenant_a):
    resp = tenant_a.client.post(
        "/api/v1/products/",
        {
            "name": "Red Pants",
            "sku": "RP-1",
            "gst_rate": "18",
            "category_name": "Apparel",
            "brand_name": "House",
            "unit_name": "CTN",
            "alternate_unit_name": "PCS",
            "conversion_rate": "12",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert resp.data["sku"] == "RP-1"
    assert resp.data["category_name"] == "Apparel"
    assert resp.data["brand_name"] == "House"
    assert resp.data["unit_name"] == "CTN"


def test_product_unit_locked_while_stock_on_hand(tenant_a):
    resp = tenant_a.client.post(
        "/api/v1/products/",
        {"name": "Soap", "sku": "SOAP-1", "gst_rate": "18", "unit_name": "PCS"},
        format="json",
    )
    product_id = resp.data["id"]
    add_stock(tenant_a, Product.objects.get(pk=product_id), "5")
    patch = tenant_a.client.patch(
        f"/api/v1/products/{product_id}/", {"unit_name": "BOX"}, format="json",
    )
    assert patch.status_code == 400, patch.data
    assert "unit" in str(patch.data).lower()


def test_product_unit_change_allowed_once_stock_is_zero(tenant_a):
    from inventory.models import MovementType
    from inventory.services import InventoryService

    resp = tenant_a.client.post(
        "/api/v1/products/",
        {"name": "Soap 2", "sku": "SOAP-2", "gst_rate": "18", "unit_name": "PCS"},
        format="json",
    )
    product_id = resp.data["id"]
    product = Product.objects.get(pk=product_id)
    add_stock(tenant_a, product, "5")
    # Bring on-hand back to zero via a compensating adjustment.
    InventoryService.post_movement(
        company=tenant_a.company, product=product,
        movement_type=MovementType.ADJUSTMENT,
        quantity=Decimal("-5"), reason="zero out for unit change", user=tenant_a.owner,
    )
    patch = tenant_a.client.patch(
        f"/api/v1/products/{product_id}/", {"unit_name": "BOX"}, format="json",
    )
    assert patch.status_code == 200, patch.data
    assert patch.data["unit_name"] == "BOX"


def test_product_unit_change_clears_stale_alternate_unit(tenant_a):
    """conversion_rate only makes sense relative to the base unit it was set
    up against; changing the base unit must not leave a stale ratio behind."""
    from inventory.models import MovementType
    from inventory.services import InventoryService

    resp = tenant_a.client.post(
        "/api/v1/products/",
        {
            "name": "Soap 3", "sku": "SOAP-3", "gst_rate": "18",
            "unit_name": "PCS", "alternate_unit_name": "CARTON", "conversion_rate": "48",
        },
        format="json",
    )
    assert resp.data["conversion_rate"] == "48.0000" or Decimal(str(resp.data["conversion_rate"])) == Decimal("48")
    product_id = resp.data["id"]
    product = Product.objects.get(pk=product_id)
    add_stock(tenant_a, product, "5")
    InventoryService.post_movement(
        company=tenant_a.company, product=product,
        movement_type=MovementType.ADJUSTMENT,
        quantity=Decimal("-5"), reason="zero out for unit change", user=tenant_a.owner,
    )
    # Patch only the base unit -- the frontend would still echo back the old
    # alternate_unit_name/conversion_rate, but even if a caller resends them
    # unchanged, the base unit change must win and clear the stale pairing.
    patch = tenant_a.client.patch(
        f"/api/v1/products/{product_id}/",
        {"unit_name": "KG", "alternate_unit_name": "CARTON", "conversion_rate": "48"},
        format="json",
    )
    assert patch.status_code == 200, patch.data
    assert patch.data["unit_name"] == "KG"
    assert not patch.data.get("alternate_unit_name")
    assert Decimal(str(patch.data["conversion_rate"])) == Decimal("1")


def test_hsn_search_includes_rate_and_description(tenant_a):
    rows = search_hsn("trouser", kind="HSN")
    assert rows
    assert rows[0]["code"]
    assert rows[0]["description"]
    assert "kind" in rows[0]
    biscuits = search_hsn("1905", kind="HSN")
    assert biscuits
    assert biscuits[0].get("gst_rate") == "5"


def test_adjustment_accepts_batch_no_for_tracked_product(tenant_a):
    from inventory.services import InventoryService

    product = make_product(tenant_a.company, sku="BATCH-ADJ", track_batch=True)
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    resp = tenant_a.client.post(
        "/api/v1/inventory/adjustments/",
        {
            "product": product.id,
            "quantity": "4",
            "reason": "Opening Stock Correction",
            "warehouse": warehouse.id,
            "batch_no": "LOT-A",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert BatchLot.objects.filter(product=product, batch_no="LOT-A").exists()
    assert StockMovement.objects.filter(product=product, movement_type=MovementType.ADJUSTMENT).exists()


def test_adjustment_still_requires_batch_when_tracked(tenant_a):
    product = make_product(tenant_a.company, sku="BATCH-MISS", name="RED Pants 2s _NB", track_batch=True)
    resp = tenant_a.client.post(
        "/api/v1/inventory/adjustments/",
        {"product": product.id, "quantity": "1", "reason": "Physical Count Discrepancy"},
        format="json",
    )
    assert resp.status_code == 400
    assert "batch" in str(resp.data).lower()


def test_stock_valuation_basis_mrp(tenant_a):
    product = make_product(
        tenant_a.company, sku="VAL-1", purchase_price="10", selling_price="20", mrp=Decimal("30"),
    )
    add_stock(tenant_a, product, "2", unit_cost="8")
    cost = tenant_a.client.get("/api/v1/inventory/valuation/")
    assert cost.status_code == 200
    mrp = tenant_a.client.get("/api/v1/inventory/valuation/", {"basis": "mrp"})
    assert mrp.status_code == 200
    assert mrp.data["basis"] == "mrp"
    rows = mrp.data["items"]
    assert rows
    row = next(r for r in rows if r["product"] == product.id or r.get("product_name") == product.name)
    assert Decimal(str(row["unit_cost"])) == Decimal("30")
    assert Decimal(str(row["value"])) == Decimal("60")
