"""INV-WP-15 — expiry alerts: what can actually be written off, what it is worth, and why (review #18)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import CompanyUser, User
from inventory.models import BatchLot, StockBalance, StockMovement
from inventory.services import InventoryService
from tests.conftest import make_product

pytestmark = pytest.mark.django_db

URL = "/api/v1/inventory/alerts/expiry/"


def _lot(tenant, sku, *, qty, days, cost="20", name="Milk"):
    product = make_product(tenant.company, sku=sku, name=name, track_batch=True, purchase_price="30")
    InventoryService.post_opening(
        company=tenant.company, product=product, quantity=qty, unit_cost=Decimal(cost), batch_no=f"{sku}-L1",
        expiry_date=date.today() + timedelta(days=max(days, 1)), user=tenant.owner,
    )
    balance = StockBalance.objects.get(company=tenant.company, product=product)
    if days < 1:
        # A lot cannot be received already expired; it goes off while it sits on the shelf.
        BatchLot.objects.filter(pk=balance.batch_id).update(expiry_date=date.today() + timedelta(days=days))
    return product, balance


def _items(client, **params):
    resp = client.get(URL, params)
    assert resp.status_code == 200, resp.data
    return resp.data["items"]


def _sales_user(tenant):
    user = User.objects.create_user(email="sales-wp15@alpha.test", password="StrongPass123!")
    CompanyUser.objects.create(
        company=tenant.company, user=user, role=CompanyUser.Role.SALES_STAFF, can_create_sales=True,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_rows_say_what_can_be_written_off_and_what_it_is_worth(tenant_a):
    product, balance = _lot(tenant_a, "EX-1", qty=10, days=5, cost="20")
    StockBalance.objects.filter(pk=balance.pk).update(reserved=Decimal("3"))
    row = _items(tenant_a.client, days=30)[0]
    assert row["product"] == product.id
    assert Decimal(row["on_hand"]) == 10 and Decimal(row["reserved"]) == 3 and Decimal(row["available"]) == 7
    assert Decimal(row["unit_cost"]) == Decimal("20")
    assert Decimal(row["value"]) == Decimal("140.00")
    assert row["expired"] is False and row["days_to_expiry"] == 5


def test_expired_lots_are_marked_and_come_first(tenant_a):
    _lot(tenant_a, "EX-2", qty=4, days=-3, name="Old milk")
    _lot(tenant_a, "EX-3", qty=4, days=10, name="New milk")
    rows = _items(tenant_a.client, days=30)
    assert [r["product_name"] for r in rows] == ["Old milk", "New milk"]
    assert rows[0]["expired"] is True and rows[0]["days_to_expiry"] == -3


def test_cost_is_for_the_owner_not_for_a_salesperson(tenant_a):
    _lot(tenant_a, "EX-4", qty=4, days=3)
    row = _items(_sales_user(tenant_a), days=30)[0]
    assert row["unit_cost"] is None and row["value"] is None
    assert row["available"] is not None


def test_written_off_stock_names_its_reason(tenant_a):
    product, balance = _lot(tenant_a, "EX-5", qty=10, days=-1)
    body = {"product": product.id, "warehouse": balance.warehouse_id, "batch": balance.batch_id, "quantity": 4}
    damaged = tenant_a.client.post(URL, {**body, "reason": "DAMAGED"}, format="json")
    assert damaged.status_code == 201, damaged.data
    assert StockMovement.objects.get(pk=damaged.data["id"]).reason == "DAMAGED"
    default = tenant_a.client.post(URL, body, format="json")
    assert StockMovement.objects.get(pk=default.data["id"]).reason == "EXPIRED"
    assert tenant_a.client.post(URL, {**body, "reason": "BECAUSE"}, format="json").status_code == 400


def test_stock_held_for_orders_cannot_be_written_off(tenant_a):
    product, balance = _lot(tenant_a, "EX-6", qty=10, days=-1)
    StockBalance.objects.filter(pk=balance.pk).update(reserved=Decimal("6"))
    body = {"product": product.id, "warehouse": balance.warehouse_id, "batch": balance.batch_id}
    too_much = tenant_a.client.post(URL, {**body, "quantity": 8}, format="json")
    assert too_much.status_code == 400
    assert "only 4" in str(too_much.data)
    ok = tenant_a.client.post(URL, {**body, "quantity": 4}, format="json")
    assert ok.status_code == 201, ok.data
