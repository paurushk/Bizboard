"""INV-IDR-12 - who may open which inventory screen's data, and who may see what things cost.

The matrix below is written out by hand (not read back from the permission classes), so a change to a
role's reach shows up as a failing row here and has to be a deliberate change.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import CompanyUser, User
from inventory.models import BatchLot, MovementType, Warehouse, WarehouseReorderLevel
from inventory.services import InventoryService
from masters.models import Supplier
from tests.conftest import add_stock, make_product

pytestmark = pytest.mark.django_db

ROLES = ["OWNER", "MANAGER", "INVENTORY_STAFF", "SALES_STAFF", "ACCOUNTANT", "AUDITOR", "VIEWER"]

# role -> may read stock, may use the inventory tools, may read the books
READ = {"OWNER", "MANAGER", "INVENTORY_STAFF", "SALES_STAFF", "ACCOUNTANT", "AUDITOR"}
MANAGE = {"OWNER", "MANAGER", "INVENTORY_STAFF"}
BOOKS = {"OWNER", "MANAGER", "ACCOUNTANT", "AUDITOR"}
CATALOGUE = READ  # everyone but a viewer
SERIAL_LOOKUP = {"OWNER", "MANAGER", "INVENTORY_STAFF", "SALES_STAFF"}  # the counter looks a serial up

# (screen, url, who may open it)
SCREENS = [
    ("Products", "/api/v1/products/", CATALOGUE),
    ("Current stock", "/api/v1/inventory/balances/", READ),
    ("Current stock (grouped)", "/api/v1/inventory/balances/by-product/", READ),
    ("Stock ledger", "/api/v1/inventory/movements/", READ),
    ("Low stock", "/api/v1/inventory/alerts/", READ),
    ("Expiry alerts", "/api/v1/inventory/alerts/expiry/", READ),
    ("Purchase planning", "/api/v1/inventory/purchase-planning/", READ),
    ("Demand forecast", "/api/v1/inventory/demand-forecast/", READ),
    ("Godowns (list)", "/api/v1/inventory/warehouses/", READ),
    ("Stock transfers", "/api/v1/inventory/transfers/", MANAGE),
    ("Stock counts", "/api/v1/inventory/stock-counts/", MANAGE),
    ("Serial numbers (lookup)", "/api/v1/inventory/serials/", SERIAL_LOOKUP),
    # BB-100 F7: anyone who sells or buys picks a lot on the line; a lot carries no cost.
    ("Batches", "/api/v1/inventory/batches/", READ),
    ("Reorder rules", "/api/v1/inventory/reorder-levels/", MANAGE),
    ("Stock valuation", "/api/v1/inventory/valuation/", BOOKS),
]


@pytest.fixture
def world(tenant_a):
    tenant_a.company.feature_flags = {"ENABLE_PURCHASE_PLANNING": True, "ENABLE_REPLENISHMENT": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    main = InventoryService.default_warehouse(tenant_a.company)
    north = Warehouse.objects.create(company=tenant_a.company, name="North", code="R12")
    supplier = Supplier.objects.create(company=tenant_a.company, name="Mega", state="Karnataka")
    product = make_product(tenant_a.company, sku="R12-1", name="Costed", reorder_level="50", purchase_price="42")
    add_stock(tenant_a, product, "20")
    lot = BatchLot.objects.create(
        company=tenant_a.company, product=product, batch_no="R12-B", expiry_date=timezone.localdate() + timedelta(days=10),
    )
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=north, product=product, batch=lot, movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("5"), unit_cost=Decimal("42"), user=tenant_a.owner,
    )
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=main, product=product, movement_type=MovementType.SALE,
        quantity=Decimal("6"), unit_cost=Decimal("42"), user=tenant_a.owner,
    )
    WarehouseReorderLevel.objects.create(
        company=tenant_a.company, warehouse=north, product=product, reorder_level=Decimal("30"),
    )
    count = tenant_a.client.post(
        "/api/v1/inventory/stock-counts/", {"warehouse": main.id, "notes": "r12"}, format="json",
    )
    assert count.status_code == 201, count.data
    return tenant_a, product, count.data["id"]


def _client_for(tenant, role):
    if role == "OWNER":
        return tenant.client
    user = User.objects.create_user(email=f"{role.lower()}-r12@alpha.test", password="StrongPass123!")
    flags = CompanyUser.capability_defaults_for_role(role) or {}
    CompanyUser.objects.create(company=tenant.company, user=user, role=role, **flags)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.parametrize("role", ROLES)
def test_role_matrix_for_every_inventory_screen(world, role):
    tenant, *_ = world
    client = _client_for(tenant, role)
    wrong = []
    for screen, url, allowed in SCREENS:
        status = client.get(url).status_code
        expect_ok = role in allowed
        if expect_ok and status != 200:
            wrong.append(f"{screen}: {role} should open it, got {status}")
        if not expect_ok and status not in (401, 403):
            wrong.append(f"{screen}: {role} should be refused, got {status}")
    assert not wrong, "\n".join(wrong)


@pytest.mark.parametrize("role", ROLES)
def test_role_matrix_for_the_inventory_writes(world, role):
    tenant, product, count_id = world
    client = _client_for(tenant, role)
    adjust = client.post(
        "/api/v1/inventory/adjustments/", {"product": product.id, "quantity": "1", "reason": "r12"}, format="json",
    ).status_code
    cancel = client.post(f"/api/v1/inventory/stock-counts/{count_id}/cancel/", {}, format="json").status_code
    new_godown = client.post("/api/v1/inventory/warehouses/", {"name": f"G-{role}", "code": f"G{role[:5]}"}, format="json").status_code
    new_lot = client.post(
        "/api/v1/inventory/batches/", {"product": product.id, "batch_no": f"L-{role}"}, format="json",
    ).status_code
    if role in MANAGE:
        assert new_lot == 201, new_lot
        assert adjust in (200, 201, 202), adjust
        assert cancel == 200, cancel
        assert new_godown == 201, new_godown
    else:
        assert adjust in (401, 403), adjust
        assert cancel in (401, 403, 404), cancel
        assert new_godown in (401, 403), new_godown
        assert new_lot in (401, 403), new_lot


# --------------------------------------------------------------------------- cost visibility

# What an item cost, or what stock is worth. selling_price and mrp are what a customer pays: fine.
COST_KEYS = {
    "unit_cost", "cost", "avg_cost", "landed_cost", "purchase_price", "last_price", "master_price",
    "stock_value", "value", "valuation", "variance_value_estimate", "value_estimate", "margin", "total_value",
}


def _cost_keys(payload, path=""):
    found = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            here = f"{path}.{key}"
            if key in COST_KEYS and value not in (None, "", [], {}):
                found.append(here)
            found.extend(_cost_keys(value, here))
    elif isinstance(payload, list):
        for i, value in enumerate(payload[:50]):
            found.extend(_cost_keys(value, f"{path}[{i}]"))
    return found


def _cost_urls(count_id, product_id):
    return [
        "/api/v1/products/",
        f"/api/v1/products/{product_id}/",
        "/api/v1/inventory/balances/",
        "/api/v1/inventory/balances/by-product/",
        "/api/v1/inventory/movements/",
        f"/api/v1/inventory/movements/?product={product_id}",
        "/api/v1/inventory/alerts/",
        "/api/v1/inventory/alerts/expiry/",
        "/api/v1/inventory/purchase-planning/",
        "/api/v1/inventory/demand-forecast/",
    ]


def test_a_salesperson_sees_no_cost_in_any_inventory_response(world):
    tenant, product, count_id = world
    client = _client_for(tenant, "SALES_STAFF")
    leaks = {}
    for url in _cost_urls(count_id, product.id):
        resp = client.get(url)
        assert resp.status_code == 200, (url, resp.status_code)
        found = _cost_keys(resp.data)
        if found:
            leaks[url] = found[:4]
    assert not leaks, leaks


def test_the_count_sheet_hides_what_the_difference_is_worth_from_a_salesperson(world):
    tenant, _product, count_id = world
    # A salesperson cannot open counts at all (inventory permission); the review is not theirs.
    client = _client_for(tenant, "SALES_STAFF")
    assert client.get(f"/api/v1/inventory/stock-counts/{count_id}/review/").status_code in (401, 403)


def test_a_buyer_still_sees_the_last_price_in_planning(world):
    tenant, product, _count_id = world
    client = _client_for(tenant, "INVENTORY_STAFF")  # raises purchases: needs the price to plan
    rows = client.get("/api/v1/inventory/purchase-planning/").data["rows"]
    assert rows and rows[0]["last_price"] not in (None, "")


def test_the_owner_sees_costs(world):
    tenant, product, _count_id = world
    movements = tenant.client.get(f"/api/v1/inventory/movements/?product={product.id}").data
    assert _cost_keys(movements) != []


@pytest.mark.parametrize("role", ROLES)
def test_only_inventory_roles_can_give_an_item_a_barcode(world, role):
    tenant, product, _count_id = world
    client = _client_for(tenant, role)
    resp = client.post("/api/v1/products/generate-barcode/", {"product": product.id}, format="json")
    product.refresh_from_db()
    if role in MANAGE:
        assert resp.status_code == 200, resp.data
        assert product.barcode
    else:
        assert resp.status_code in (401, 403)
        assert not product.barcode
