"""INV-IDR-08 - one pace of sales, a donor that can only give its surplus, orders counted once."""

from __future__ import annotations

from datetime import timedelta
from decimal import ROUND_CEILING, Decimal

import pytest
from django.utils import timezone

from inventory import planning_settings as ps
from inventory.forecast import demand_forecast, godown_velocity, item_velocity, overstock_rows
from inventory.models import MovementType, Warehouse, WarehouseReorderLevel
from inventory.reorder_maps import open_order_quantities
from inventory.services import InventoryService
from masters.models import Product, Supplier
from purchases.models import PurchaseOrder
from tests.conftest import make_product

pytestmark = pytest.mark.django_db

PLAN = "/api/v1/inventory/purchase-planning/"
FORECAST = "/api/v1/inventory/demand-forecast/"


@pytest.fixture
def planned(tenant_a):
    tenant_a.company.feature_flags = {"ENABLE_PURCHASE_PLANNING": True, "ENABLE_REPLENISHMENT": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    return tenant_a


def _move(tenant, product, kind, qty, days_ago=0, warehouse=None):
    InventoryService.post_movement(
        company=tenant.company, product=product, movement_type=kind, quantity=Decimal(qty),
        unit_cost=Decimal("10"), user=tenant.owner, warehouse=warehouse,
        movement_date=timezone.localdate() - timedelta(days=days_ago),
    )


def _rows(resp):
    assert resp.status_code == 200, resp.data
    return {row["product_name"]: row for row in resp.data["rows"]}


# --------------------------------------------------------------------------- F-14 / F-17: one pace

def test_days_out_of_stock_do_not_dilute_the_pace(tenant_a):
    """Stock only for the last 10 days, 20 sold in them: 2 a day, not 20 over 30 days."""
    product = make_product(tenant_a.company, sku="N8-A", name="Seasonal")
    _move(tenant_a, product, MovementType.OPENING_STOCK, "25", days_ago=9)
    _move(tenant_a, product, MovementType.SALE, "20", days_ago=2)
    row = next(r for r in demand_forecast(tenant_a.company) if r["product_name"] == "Seasonal")
    assert row["method"] == "in_stock_days_mean"
    assert row["in_stock_days"] == 10
    assert Decimal(row["daily_rate"]) == Decimal("2.000")
    assert item_velocity(tenant_a.company)[product.id] == Decimal("2.000")


def test_too_little_history_falls_back_to_the_flat_mean(tenant_a):
    product = make_product(tenant_a.company, sku="N8-B", name="NewItem")
    _move(tenant_a, product, MovementType.OPENING_STOCK, "100", days_ago=0)
    _move(tenant_a, product, MovementType.SALE, "30", days_ago=0)
    row = next(r for r in demand_forecast(tenant_a.company) if r["product_name"] == "NewItem")
    assert row["method"] == "trailing_mean_net"
    assert Decimal(row["daily_rate"]) == Decimal("1.000")


def test_forecast_planning_and_reorder_hint_agree_for_the_same_item(planned):
    product = make_product(planned.company, sku="N8-C", name="Agree", reorder_level="50")
    _move(planned, product, MovementType.OPENING_STOCK, "100", days_ago=15)
    _move(planned, product, MovementType.SALE, "60", days_ago=1)
    Supplier.objects.create(company=planned.company, name="Mega", state="Karnataka")
    forecast = next(r for r in demand_forecast(planned.company) if r["product_name"] == "Agree")
    plan_row = _rows(planned.client.get(PLAN))["Agree"]
    assert plan_row["days_to_stockout"] == forecast["days_of_cover"]
    assert Decimal(forecast["suggested_reorder_level"]) == (Decimal(forecast["daily_rate"]) * 14).to_integral_value(rounding=ROUND_CEILING)


def test_the_pace_at_a_godown_uses_the_same_definition(tenant_a):
    main = InventoryService.default_warehouse(tenant_a.company)
    north = Warehouse.objects.create(company=tenant_a.company, name="North", code="N8N")
    product = make_product(tenant_a.company, sku="N8-D", name="Godowned")
    _move(tenant_a, product, MovementType.OPENING_STOCK, "100", days_ago=20, warehouse=north)
    _move(tenant_a, product, MovementType.SALE, "40", days_ago=1, warehouse=north)
    _move(tenant_a, product, MovementType.OPENING_STOCK, "100", days_ago=0, warehouse=main)
    pace = godown_velocity(tenant_a.company, [north.id, main.id])
    assert pace[(product.id, north.id)] == Decimal("1.905")  # 40 over 21 in-stock days
    assert (product.id, main.id) not in pace


def test_inactive_and_unstocked_items_are_not_forecast(tenant_a):
    inactive = make_product(tenant_a.company, sku="N8-E", name="Gone")
    _move(tenant_a, inactive, MovementType.OPENING_STOCK, "50", days_ago=0)
    _move(tenant_a, inactive, MovementType.SALE, "10", days_ago=0)
    Product.objects.filter(pk=inactive.pk).update(status=Product.Status.INACTIVE)
    service = make_product(tenant_a.company, sku="N8-F", name="Service")
    _move(tenant_a, service, MovementType.OPENING_STOCK, "50", days_ago=0)
    _move(tenant_a, service, MovementType.SALE, "10", days_ago=0)
    Product.objects.filter(pk=service.pk).update(track_inventory=False)
    names = {r["product_name"] for r in demand_forecast(tenant_a.company)}
    assert "Gone" not in names and "Service" not in names


def test_company_settings_change_the_cover_and_bad_values_are_ignored(tenant_a):
    product = make_product(tenant_a.company, sku="N8-G", name="Tuned")
    _move(tenant_a, product, MovementType.OPENING_STOCK, "100", days_ago=0)
    _move(tenant_a, product, MovementType.SALE, "30", days_ago=0)
    tenant_a.company.feature_flags = {ps.FORECAST_COVER_DAYS: 60, ps.REORDER_COVER_DAYS: "nonsense"}
    tenant_a.company.save(update_fields=["feature_flags"])
    row = next(r for r in demand_forecast(tenant_a.company) if r["product_name"] == "Tuned")
    assert row["cover_days_target"] == 60
    assert row["reorder_cover_days"] == 14  # default: the setting was not a number


def test_overstock_lists_items_with_no_sales_or_endless_cover(tenant_a):
    idle = make_product(tenant_a.company, sku="N8-H", name="Idle")
    _move(tenant_a, idle, MovementType.OPENING_STOCK, "500", days_ago=40)
    busy = make_product(tenant_a.company, sku="N8-I", name="Busy")
    _move(tenant_a, busy, MovementType.OPENING_STOCK, "60", days_ago=40)
    _move(tenant_a, busy, MovementType.SALE, "30", days_ago=1)
    slow = make_product(tenant_a.company, sku="N8-J", name="Slow")
    _move(tenant_a, slow, MovementType.OPENING_STOCK, "2000", days_ago=40)
    _move(tenant_a, slow, MovementType.SALE, "9", days_ago=1)
    rows = {r["product_name"]: r for r in overstock_rows(tenant_a.company)}
    assert rows["Idle"]["no_sales"] is True
    assert "Busy" not in rows
    assert rows["Slow"]["days_of_cover"] > 180
    assert "overstock" in tenant_a.client.get(FORECAST).data


# --------------------------------------------------------------------------- F-15: donor cap

def test_a_donor_with_a_small_surplus_moves_that_much_and_the_rest_is_bought(planned):
    main = InventoryService.default_warehouse(planned.company)
    north = Warehouse.objects.create(company=planned.company, name="North", code="N8M")
    rice = make_product(planned.company, sku="N8-R", name="Rice", reorder_level="10")
    _move(planned, rice, MovementType.OPENING_STOCK, "12", warehouse=main)   # 2 above its rule of 10
    _move(planned, rice, MovementType.OPENING_STOCK, "2", warehouse=north)
    WarehouseReorderLevel.objects.create(
        company=planned.company, warehouse=north, product=rice, reorder_level=Decimal("10"),
    )
    Supplier.objects.create(company=planned.company, name="Mega", state="Karnataka")
    plan = planned.client.get(PLAN).data
    rice_rows = [r for r in plan["rows"] if r["product_name"] == "Rice"]
    transfer = next(r for r in rice_rows if r["transfer_from_warehouse_id"])
    purchase = next(r for r in rice_rows if not r["transfer_from_warehouse_id"])
    assert transfer["transfer_from_warehouse_id"] == main.id
    assert Decimal(transfer["suggested_qty"]) == Decimal("2")
    assert Decimal(purchase["suggested_qty"]) == Decimal("6")
    assert transfer["warehouse_id"] == purchase["warehouse_id"] == north.id


def test_the_in_transit_godown_is_never_a_donor(planned):
    from inventory.services import StockTransferService

    north = Warehouse.objects.create(company=planned.company, name="North", code="N8T")
    transit = StockTransferService.in_transit_warehouse(planned.company)
    oil = make_product(planned.company, sku="N8-O", name="Oil", reorder_level="5")
    _move(planned, oil, MovementType.OPENING_STOCK, "100", warehouse=transit)
    _move(planned, oil, MovementType.OPENING_STOCK, "1", warehouse=north)
    WarehouseReorderLevel.objects.create(
        company=planned.company, warehouse=north, product=oil, reorder_level=Decimal("5"),
    )
    rows = [r for r in planned.client.get(PLAN).data["rows"] if r["product_name"] == "Oil"]
    assert rows and all(not r["transfer_from_warehouse_id"] for r in rows)


# --------------------------------------------------------------------------- F-16: open orders

def _draft_po(tenant, supplier, product, qty, age_days=0):
    from purchases.models import PurchaseOrderItem

    order = PurchaseOrder.objects.create(company=tenant.company, supplier=supplier)
    PurchaseOrderItem.objects.create(
        company=tenant.company, purchase_order=order, product=product, quantity=Decimal(qty),
        unit_price=Decimal("10"), gst_rate=Decimal("0"),
    )
    if age_days:
        PurchaseOrder.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(days=age_days))
    return order


def test_old_forgotten_drafts_are_listed_but_not_counted(planned):
    supplier = Supplier.objects.create(company=planned.company, name="Mega", state="Karnataka")
    tea = make_product(planned.company, sku="N8-T", name="Tea", reorder_level="10")
    _move(planned, tea, MovementType.OPENING_STOCK, "3")
    _draft_po(planned, supplier, tea, "50", age_days=90)
    counted, stale = open_order_quantities(planned.company, [tea.id])
    assert counted == {} and stale[tea.id] == Decimal("50")
    plan = planned.client.get(PLAN).data
    assert Decimal(next(r for r in plan["rows"] if r["product_name"] == "Tea")["suggested_qty"]) == Decimal("7")
    assert [(d["product_id"], Decimal(d["quantity"])) for d in plan["stale_drafts"]] == [(tea.id, Decimal("50"))]


def test_a_recent_draft_is_counted_and_the_window_is_a_company_setting(planned):
    supplier = Supplier.objects.create(company=planned.company, name="Mega", state="Karnataka")
    tea = make_product(planned.company, sku="N8-T2", name="Tea", reorder_level="10")
    _draft_po(planned, supplier, tea, "4", age_days=10)
    assert open_order_quantities(planned.company, [tea.id])[0][tea.id] == Decimal("4")
    planned.company.feature_flags = {**planned.company.feature_flags, ps.PLANNING_DRAFT_PO_DAYS: 5}
    planned.company.save(update_fields=["feature_flags"])
    counted, stale = open_order_quantities(planned.company, [tea.id])
    assert counted == {} and stale[tea.id] == Decimal("4")


def test_the_same_key_creates_the_drafts_once(planned):
    supplier = Supplier.objects.create(company=planned.company, name="Mega", state="Karnataka")
    tea = make_product(planned.company, sku="N8-T3", name="Tea", reorder_level="10")
    body = {"rows": [{"product_id": tea.id, "suggested_qty": "4", "supplier_id": supplier.id}]}
    first = planned.client.post(PLAN, body, format="json", HTTP_IDEMPOTENCY_KEY="n8-plan-1")
    second = planned.client.post(PLAN, body, format="json", HTTP_IDEMPOTENCY_KEY="n8-plan-1")
    assert first.status_code == second.status_code == 200
    assert second.data["purchase_order_ids"] == first.data["purchase_order_ids"]
    assert PurchaseOrder.objects.filter(company=planned.company).count() == 1


def test_a_second_draft_for_the_same_item_and_supplier_needs_confirmation(planned):
    supplier = Supplier.objects.create(company=planned.company, name="Mega", state="Karnataka")
    tea = make_product(planned.company, sku="N8-T4", name="Tea", reorder_level="10")
    row = {"product_id": tea.id, "suggested_qty": "4", "supplier_id": supplier.id}
    assert planned.client.post(PLAN, {"rows": [row]}, format="json", HTTP_IDEMPOTENCY_KEY="n8-a").status_code == 200
    refused = planned.client.post(PLAN, {"rows": [row]}, format="json", HTTP_IDEMPOTENCY_KEY="n8-b")
    assert refused.status_code == 400
    assert refused.data["code"] == "duplicate_draft"
    assert PurchaseOrder.objects.filter(company=planned.company).count() == 1
    again = planned.client.post(
        PLAN, {"rows": [row], "confirm_duplicate": True}, format="json", HTTP_IDEMPOTENCY_KEY="n8-c",
    )
    assert again.status_code == 200
    assert PurchaseOrder.objects.filter(company=planned.company).count() == 2


def test_the_row_carries_both_the_last_bought_price_and_the_master_price(planned):
    tea = make_product(planned.company, sku="N8-P", name="Priced", reorder_level="10")
    _move(planned, tea, MovementType.OPENING_STOCK, "3")
    Supplier.objects.create(company=planned.company, name="Mega", state="Karnataka")
    row = _rows(planned.client.get(PLAN))["Priced"]
    assert "master_price" in row and "last_price" in row
    assert row["last_price"] == row["master_price"]  # never bought: the item master's price
