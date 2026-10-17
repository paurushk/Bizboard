"""INV-WP-14 — godown management: rename, reactivate, change the default, hide the system godown (review #16)."""

from __future__ import annotations

import pytest

from inventory.models import Warehouse
from inventory.services import InventoryService, StockTransferService
from tests.conftest import add_stock, make_product

pytestmark = pytest.mark.django_db

WH = "/api/v1/inventory/warehouses/"


def _rows(resp):
    assert resp.status_code == 200, resp.data
    return resp.data["results"] if isinstance(resp.data, dict) and "results" in resp.data else resp.data


@pytest.fixture
def shop(tenant_a):
    main = InventoryService.default_warehouse(tenant_a.company)
    north = Warehouse.objects.create(company=tenant_a.company, name="North", code="NR")
    return tenant_a, main, north


def test_the_in_transit_godown_is_not_listed_or_reachable(shop):
    tenant, main, north = shop
    transit = StockTransferService.in_transit_warehouse(tenant.company)
    assert transit.is_system is True
    names = {r["name"] for r in _rows(tenant.client.get(WH))}
    assert names == {"Default Godown", "North"}
    assert tenant.client.get(f"{WH}{transit.id}/").status_code == 404
    assert tenant.client.patch(f"{WH}{transit.id}/", {"name": "x"}, format="json").status_code == 404
    assert tenant.client.delete(f"{WH}{transit.id}/").status_code == 404


def test_nothing_can_be_counted_adjusted_or_moved_into_the_in_transit_godown(shop):
    tenant, main, north = shop
    transit = StockTransferService.in_transit_warehouse(tenant.company)
    product = make_product(tenant.company, sku="WH-1")
    add_stock(tenant, product, "10")
    adj = tenant.client.post(
        "/api/v1/inventory/adjustments/",
        {"product": product.id, "quantity": "1", "reason": "x", "warehouse": transit.id}, format="json",
    )
    assert adj.status_code == 400
    count = tenant.client.post("/api/v1/inventory/stock-counts/", {"warehouse": transit.id}, format="json")
    assert count.status_code == 400
    transfer = tenant.client.post(
        "/api/v1/inventory/transfers/",
        {"from_warehouse": main.id, "to_warehouse": transit.id, "lines": [{"product": product.id, "quantity": "1"}]},
        format="json",
    )
    assert transfer.status_code == 400
    opening = tenant.client.post(
        "/api/v1/inventory/opening-stock/",
        {"product": product.id, "quantity": 1, "warehouse": transit.id}, format="json",
    )
    assert opening.status_code == 400


def test_a_godown_can_be_renamed_but_not_to_a_name_or_code_already_taken(shop):
    tenant, main, north = shop
    ok = tenant.client.patch(f"{WH}{north.id}/", {"name": "North yard", "code": "NY"}, format="json")
    assert ok.status_code == 200, ok.data
    north.refresh_from_db()
    assert (north.name, north.code) == ("North yard", "NY")
    clash_name = tenant.client.patch(f"{WH}{north.id}/", {"name": "default godown"}, format="json")
    assert clash_name.status_code == 400
    clash_code = tenant.client.patch(f"{WH}{north.id}/", {"code": main.code.lower()}, format="json")
    assert clash_code.status_code == 400
    # saving a godown under its own name and code is not a clash
    assert tenant.client.patch(f"{WH}{north.id}/", {"name": "North yard"}, format="json").status_code == 200


def test_making_a_godown_the_default_moves_the_default(shop):
    tenant, main, north = shop
    resp = tenant.client.patch(f"{WH}{north.id}/", {"is_default": True}, format="json")
    assert resp.status_code == 200, resp.data
    main.refresh_from_db()
    north.refresh_from_db()
    assert north.is_default is True and main.is_default is False
    assert Warehouse.objects.filter(company=tenant.company, is_default=True).count() == 1


def test_a_switched_off_godown_cannot_be_the_default_and_can_be_switched_back_on(shop):
    tenant, main, north = shop
    off = tenant.client.patch(f"{WH}{north.id}/", {"is_active": False}, format="json")
    assert off.status_code == 200, off.data
    refused = tenant.client.patch(f"{WH}{north.id}/", {"is_default": True}, format="json")
    assert refused.status_code == 400
    on = tenant.client.patch(f"{WH}{north.id}/", {"is_active": True}, format="json")
    assert on.status_code == 200
    north.refresh_from_db()
    assert north.is_active is True


def test_the_default_godown_cannot_be_switched_off_or_deleted(shop):
    tenant, main, north = shop
    assert tenant.client.patch(f"{WH}{main.id}/", {"is_active": False}, format="json").status_code == 400
    assert tenant.client.delete(f"{WH}{main.id}/").status_code == 400


def test_a_godown_with_no_history_can_be_deleted_and_one_with_history_cannot(shop):
    tenant, main, north = shop
    product = make_product(tenant.company, sku="WH-2")
    add_stock(tenant, product, "5")
    from inventory.models import MovementType
    InventoryService.post_movement(
        company=tenant.company, product=product, movement_type=MovementType.OPENING_STOCK,
        quantity=3, unit_cost=10, user=tenant.owner, warehouse=north,
    )
    refused = tenant.client.delete(f"{WH}{north.id}/")
    assert refused.status_code == 400
    empty = Warehouse.objects.create(company=tenant.company, name="Spare", code="SP")
    assert tenant.client.delete(f"{WH}{empty.id}/").status_code in (200, 204)
