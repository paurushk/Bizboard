"""INV-WP-10 — one sales-pace definition for the forecast and for planning (inventory review #19, #29)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from inventory.forecast import COVER_DAYS, WINDOW_DAYS, demand_forecast, item_velocity
from inventory.models import MovementType
from inventory.services import InventoryService
from masters.models import Supplier
from tests.conftest import add_stock, make_product

pytestmark = pytest.mark.django_db

FORECAST = "/api/v1/inventory/demand-forecast/"
PLAN = "/api/v1/inventory/purchase-planning/"


def _move(tenant, product, kind, qty):
    InventoryService.post_movement(
        company=tenant.company, product=product, movement_type=kind, quantity=Decimal(qty),
        unit_cost=Decimal("10"), user=tenant.owner,
    )


def test_sales_returns_come_off_the_pace(tenant_a):
    product = make_product(tenant_a.company, sku="FC-1", name="Tea")
    add_stock(tenant_a, product, "500")
    _move(tenant_a, product, MovementType.SALE, "90")
    _move(tenant_a, product, MovementType.SALES_RETURN, "30")
    velocity = item_velocity(tenant_a.company)
    assert velocity[product.id] == (Decimal("60") / Decimal(WINDOW_DAYS)).quantize(Decimal("0.001"))


def test_a_product_that_only_came_back_is_not_a_seller(tenant_a):
    product = make_product(tenant_a.company, sku="FC-2")
    add_stock(tenant_a, product, "10")
    _move(tenant_a, product, MovementType.SALES_RETURN, "5")
    assert product.id not in item_velocity(tenant_a.company)


def test_rows_show_cover_and_a_suggestion_that_nets_off_stock_and_orders(tenant_a):
    fast = make_product(tenant_a.company, sku="FC-F", name="Fast")
    slow = make_product(tenant_a.company, sku="FC-S", name="Slow")
    add_stock(tenant_a, fast, "100")
    add_stock(tenant_a, slow, "1000")
    _move(tenant_a, fast, MovementType.SALE, "60")   # 2 a day, 40 left -> 20 days of cover
    _move(tenant_a, slow, MovementType.SALE, "30")   # 1 a day, 970 left -> plenty
    rows = {r["product_name"]: r for r in demand_forecast(tenant_a.company)}
    assert rows["Fast"]["window_days"] == WINDOW_DAYS
    assert rows["Fast"]["days_of_cover"] == 20
    # 30 days of cover wanted = 60 units, 40 on hand -> 20, ordered whole
    assert Decimal(rows["Fast"]["suggested_qty"]) == Decimal("20")
    assert rows["Fast"]["needs_action"] is True
    assert rows["Slow"]["needs_action"] is False and Decimal(rows["Slow"]["suggested_qty"]) == 0
    assert COVER_DAYS == 30


def test_needs_action_comes_first(tenant_a):
    fast = make_product(tenant_a.company, sku="FC-F2", name="Fast")
    slow = make_product(tenant_a.company, sku="FC-S2", name="Slow")
    add_stock(tenant_a, fast, "100")
    add_stock(tenant_a, slow, "1000")
    _move(tenant_a, slow, MovementType.SALE, "30")
    _move(tenant_a, fast, MovementType.SALE, "60")
    names = [r["product_name"] for r in demand_forecast(tenant_a.company)]
    assert names == ["Fast", "Slow"]


def test_the_api_returns_the_same_rows(tenant_a):
    product = make_product(tenant_a.company, sku="FC-A", name="Tea")
    add_stock(tenant_a, product, "100")
    _move(tenant_a, product, MovementType.SALE, "60")
    resp = tenant_a.client.get(FORECAST)
    assert resp.status_code == 200
    row = resp.data["rows"][0]
    assert row["product_name"] == "Tea" and row["method"] == "trailing_mean_net"
    assert {"available", "on_order", "days_of_cover", "suggested_qty", "needs_action"} <= set(row)


def test_planning_days_to_stockout_uses_the_same_pace(tenant_a):
    tenant_a.company.feature_flags = {"ENABLE_PURCHASE_PLANNING": True, "ENABLE_REPLENISHMENT": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    product = make_product(tenant_a.company, sku="FC-P", name="Tea", reorder_level="50")
    add_stock(tenant_a, product, "100")
    _move(tenant_a, product, MovementType.SALE, "60")  # 2 a day, 40 left, reorder 50 -> low
    Supplier.objects.create(company=tenant_a.company, name="Mega", state="Karnataka")
    plan = tenant_a.client.get(PLAN)
    assert plan.status_code == 200, plan.data
    row = next(r for r in plan.data["rows"] if r["product_name"] == "Tea")
    forecast = next(r for r in demand_forecast(tenant_a.company) if r["product_name"] == "Tea")
    assert row["days_to_stockout"] == forecast["days_of_cover"] == 20


def test_rows_suggest_a_reorder_level_that_covers_two_weeks_of_sales(tenant_a):
    from inventory.forecast import REORDER_COVER_DAYS

    product = make_product(tenant_a.company, sku="FC-R", name="Rice")
    add_stock(tenant_a, product, "500")
    _move(tenant_a, product, MovementType.SALE, "60")   # 2 a day
    row = next(r for r in demand_forecast(tenant_a.company) if r["product_name"] == "Rice")
    assert row["reorder_cover_days"] == REORDER_COVER_DAYS == 14
    assert Decimal(row["suggested_reorder_level"]) == Decimal("28")
