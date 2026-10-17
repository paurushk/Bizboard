"""INV-WP-08 — one definition of low stock for every screen and count (inventory review #20, A2).

The alerts API, the dashboard tile, the balance ``?low_stock=1`` filter and Purchase planning all read
``inventory.low_stock``. These tests build one company with every awkward case and check they agree.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from inventory.models import MovementType, StockBalance, Warehouse, WarehouseReorderLevel
from inventory.services import InventoryService
from tests.conftest import make_product

pytestmark = pytest.mark.django_db

ALERTS = "/api/v1/inventory/alerts/"
BALANCES = "/api/v1/inventory/balances/"


def _stock(tenant, product, warehouse, qty):
    InventoryService.post_movement(
        company=tenant.company, product=product, movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal(qty), unit_cost=Decimal("10"), user=tenant.owner, warehouse=warehouse,
    )


@pytest.fixture
def shop(tenant_a):
    main = InventoryService.default_warehouse(tenant_a.company)
    north = Warehouse.objects.create(company=tenant_a.company, name="North", code="NR")
    company = tenant_a.company

    low = make_product(company, sku="LOW", reorder_level="10")
    _stock(tenant_a, low, main, "3")

    fine = make_product(company, sku="FINE", reorder_level="5")
    _stock(tenant_a, fine, main, "20")

    out = make_product(company, sku="OUT", reorder_level="0")
    _stock(tenant_a, out, main, "4")
    InventoryService.post_movement(
        company=company, product=out, movement_type=MovementType.ADJUSTMENT, quantity=Decimal("-4"),
        reason="sold out", user=tenant_a.owner, warehouse=main,
    )

    godown = make_product(company, sku="GODOWN", reorder_level="0")
    _stock(tenant_a, godown, main, "50")
    _stock(tenant_a, godown, north, "2")
    WarehouseReorderLevel.objects.create(
        company=company, warehouse=north, product=godown, reorder_level=Decimal("8"),
    )

    make_product(company, sku="NEVER", reorder_level="5")  # never had a stock row

    inactive = make_product(company, sku="INACTIVE", reorder_level="10")
    _stock(tenant_a, inactive, main, "1")
    inactive.status = "INACTIVE"
    inactive.save(update_fields=["status"])

    untracked = make_product(company, sku="UNTRACKED", reorder_level="10", track_inventory=False)
    assert untracked.track_inventory is False

    reserved = make_product(company, sku="RESERVED", reorder_level="5")
    _stock(tenant_a, reserved, main, "6")
    StockBalance.objects.filter(company=company, product=reserved).update(reserved=Decimal("3"))
    return tenant_a


def _skus(resp):
    assert resp.status_code == 200, resp.data
    return {row["sku"] for row in resp.data["items"]}


def test_low_list_follows_the_rule(shop):
    assert _skus(shop.client.get(ALERTS)) == {"LOW", "GODOWN", "NEVER", "RESERVED"}


def test_out_of_stock_items_with_no_rule_are_apart_from_low(shop):
    assert _skus(shop.client.get(ALERTS, {"status": "out"})) == {"OUT"}


def test_all_is_both_and_unknown_status_is_refused(shop):
    assert _skus(shop.client.get(ALERTS, {"status": "all"})) == {"LOW", "GODOWN", "NEVER", "RESERVED", "OUT"}
    assert shop.client.get(ALERTS, {"status": "nonsense"}).status_code == 400


def test_rows_say_what_kind_of_alert_they_are(shop):
    rows = {r["sku"]: r for r in shop.client.get(ALERTS, {"status": "all"}).data["items"]}
    assert rows["LOW"]["is_warehouse_specific"] is False and rows["LOW"]["has_reorder_rule"] is True
    assert rows["GODOWN"]["is_warehouse_specific"] is True and rows["GODOWN"]["warehouse_name"] == "North"
    assert rows["OUT"]["has_reorder_rule"] is False and rows["OUT"]["stock_status"] == "OUT"
    assert rows["NEVER"]["stock_status"] == "OUT" and rows["NEVER"]["has_reorder_rule"] is True
    assert rows["RESERVED"]["stock_status"] == "LOW"
    assert Decimal(str(rows["RESERVED"]["available"])) == Decimal("3")


def test_the_dashboard_tile_counts_the_same_list(shop):
    listed = len(shop.client.get(ALERTS).data["items"])
    dash = shop.client.get("/api/v1/dashboard/")
    assert dash.status_code == 200, dash.data
    body = dash.data.get("data", dash.data)
    assert body["low_stock_count"] == listed


def test_the_balance_filter_returns_the_same_items_that_have_a_balance_row(shop):
    resp = shop.client.get(BALANCES, {"low_stock": "1"})
    assert resp.status_code == 200, resp.data
    rows = resp.data["results"] if isinstance(resp.data, dict) and "results" in resp.data else resp.data
    got = {(r["sku"], r["warehouse_name"]) for r in rows}
    skus = {sku for sku, _ in got}
    # NEVER has no balance row to return; everything else the alerts list is here.
    assert skus == {"LOW", "GODOWN", "RESERVED"}
    # the godown rule is judged at North only, not at Main where 50 are on hand
    assert ("GODOWN", "North") in got and ("GODOWN", "Default Godown") not in got


def test_planning_starts_from_the_same_rows(shop):
    from inventory.views import low_stock_alert_payload

    assert {r.product.sku for r in low_stock_alert_payload(shop.company)} == {
        "LOW", "GODOWN", "NEVER", "RESERVED",
    }
