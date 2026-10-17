"""INV-WP-09 — Purchase planning covers every low item (inventory review #25, #28; D3 = yes)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from inventory.models import MovementType, Warehouse, WarehouseReorderLevel
from inventory.services import InventoryService
from masters.models import Supplier, Unit
from purchases.models import PurchaseOrder
from tests.conftest import make_product

pytestmark = pytest.mark.django_db

PLAN = "/api/v1/inventory/purchase-planning/"


@pytest.fixture
def planned(tenant_a):
    tenant_a.company.feature_flags = {"ENABLE_PURCHASE_PLANNING": True, "ENABLE_REPLENISHMENT": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    return tenant_a


def _stock(tenant, product, warehouse, qty):
    InventoryService.post_movement(
        company=tenant.company, product=product, movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal(qty), unit_cost=Decimal("10"), user=tenant.owner, warehouse=warehouse,
    )


def _rows(resp):
    assert resp.status_code == 200, resp.data
    return {row["product_name"]: row for row in resp.data["rows"]}


def test_company_wide_low_items_are_planned_into_the_default_godown(planned):
    main = InventoryService.default_warehouse(planned.company)
    tea = make_product(planned.company, sku="PL-TEA", name="Tea", reorder_level="10")
    _stock(planned, tea, main, "3")
    rows = _rows(planned.client.get(PLAN))
    assert rows["Tea"]["scope"] == "company"
    assert rows["Tea"]["warehouse_id"] == main.id
    assert Decimal(rows["Tea"]["suggested_qty"]) == Decimal("7")
    assert Decimal(rows["Tea"]["available"]) == Decimal("3")
    assert rows["Tea"]["transfer_from_warehouse_id"] is None


def test_a_godown_rule_is_planned_into_that_godown(planned):
    main = InventoryService.default_warehouse(planned.company)
    north = Warehouse.objects.create(company=planned.company, name="North", code="NR")
    rice = make_product(planned.company, sku="PL-RICE", name="Rice", reorder_level="0")
    _stock(planned, rice, north, "2")
    WarehouseReorderLevel.objects.create(
        company=planned.company, warehouse=north, product=rice, reorder_level=Decimal("8"),
    )
    rows = _rows(planned.client.get(PLAN))
    assert rows["Rice"]["scope"] == "godown"
    assert rows["Rice"]["warehouse_name"] == "North"
    # the same low rows feed Low stock, so nothing on that page is silently missing here
    low = {r["product_name"] for r in planned.client.get("/api/v1/inventory/alerts/").data["items"]}
    assert set(rows) <= low
    assert main.id != north.id


def test_everything_low_is_planned_or_accounted_for(planned):
    main = InventoryService.default_warehouse(planned.company)
    for i in range(3):
        product = make_product(planned.company, sku=f"PL-N{i}", name=f"Item {i}", reorder_level="5")
        _stock(planned, product, main, "1")
    low = {r["product_name"] for r in planned.client.get("/api/v1/inventory/alerts/").data["items"]}
    plan = planned.client.get(PLAN)
    assert set(_rows(plan)) == low


def test_open_orders_come_off_the_suggestion_and_can_cover_it_fully(planned):
    main = InventoryService.default_warehouse(planned.company)
    tea = make_product(planned.company, sku="PL-T2", name="Tea", reorder_level="10")
    _stock(planned, tea, main, "3")
    supplier = Supplier.objects.create(company=planned.company, name="Mega", state="Karnataka")

    first = planned.client.post(
        PLAN,
        {"rows": [{"product_id": tea.id, "suggested_qty": "4", "supplier_id": supplier.id, "warehouse_name": "Default"}]},
        format="json",
    )
    assert first.status_code == 200, first.data
    row = _rows(planned.client.get(PLAN))["Tea"]
    assert Decimal(row["on_order"]) == Decimal("4")
    assert Decimal(row["suggested_qty"]) == Decimal("3")  # 7 wanted, 4 already on order

    planned.client.post(
        PLAN,
        {"rows": [{"product_id": tea.id, "suggested_qty": "3", "supplier_id": supplier.id}], "confirm_duplicate": True},
        format="json",
    )
    resp = planned.client.get(PLAN)
    assert "Tea" not in _rows(resp)
    assert resp.data["covered_by_orders"] == 1


def test_the_godown_filter_follows_the_destination(planned):
    main = InventoryService.default_warehouse(planned.company)
    north = Warehouse.objects.create(company=planned.company, name="North", code="NR")
    tea = make_product(planned.company, sku="PL-F1", name="Tea", reorder_level="10")
    _stock(planned, tea, main, "3")
    rice = make_product(planned.company, sku="PL-F2", name="Rice", reorder_level="0")
    _stock(planned, rice, north, "1")
    WarehouseReorderLevel.objects.create(
        company=planned.company, warehouse=north, product=rice, reorder_level=Decimal("6"),
    )
    assert set(_rows(planned.client.get(PLAN, {"warehouse": north.id}))) == {"Rice"}
    assert set(_rows(planned.client.get(PLAN, {"warehouse": main.id}))) == {"Tea"}


def test_the_last_supplier_is_named(planned, monkeypatch):
    main = InventoryService.default_warehouse(planned.company)
    tea = make_product(planned.company, sku="PL-S1", name="Tea", reorder_level="10")
    _stock(planned, tea, main, "3")
    supplier = Supplier.objects.create(company=planned.company, name="Mega Suppliers", state="Karnataka")
    monkeypatch.setattr("inventory.reorder_maps.last_completed_suppliers", lambda company, ids: {tea.id: supplier.id})
    row = _rows(planned.client.get(PLAN))["Tea"]
    assert row["supplier_id"] == supplier.id
    assert row["supplier_name"] == "Mega Suppliers"
    assert planned.client.get(PLAN, {"supplier": supplier.id}).data["rows"]
    assert not planned.client.get(PLAN, {"supplier": supplier.id + 99}).data["rows"]


def test_drafts_keep_the_edited_quantity_and_round_pieces_but_not_weights(planned):
    supplier = Supplier.objects.create(company=planned.company, name="Mega", state="Karnataka")
    pieces = Unit.objects.create(company=planned.company, name="Pieces", short_name="pcs", uqc_code="PCS")
    kilos = Unit.objects.create(company=planned.company, name="Kilograms", short_name="kg", uqc_code="KGS")
    soap = make_product(planned.company, sku="PL-D1", name="Soap", unit=pieces)
    flour = make_product(planned.company, sku="PL-D2", name="Flour", unit=kilos)
    resp = planned.client.post(
        PLAN,
        {"rows": [
            {"product_id": soap.id, "suggested_qty": "2.5", "supplier_id": supplier.id},
            {"product_id": flour.id, "suggested_qty": "2.5", "supplier_id": supplier.id},
        ]},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    order = PurchaseOrder.objects.get(pk=resp.data["purchase_order_ids"][0])
    qty = {item.product.name: item.quantity for item in order.items.select_related("product")}
    assert qty == {"Soap": Decimal("3.000"), "Flour": Decimal("2.500")}
    assert "Soap rounded from 2.5 to 3" in order.notes


def test_a_draft_row_without_a_quantity_is_refused(planned):
    supplier = Supplier.objects.create(company=planned.company, name="Mega", state="Karnataka")
    soap = make_product(planned.company, sku="PL-D3", name="Soap")
    resp = planned.client.post(
        PLAN, {"rows": [{"product_id": soap.id, "suggested_qty": "0", "supplier_id": supplier.id}]}, format="json",
    )
    assert resp.status_code == 400
    assert not PurchaseOrder.objects.filter(company=planned.company).exists()
