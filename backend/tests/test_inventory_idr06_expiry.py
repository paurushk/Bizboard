"""INV-IDR-06 - expiry write-off: one write-off per key, bad input is a message not a crash."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from inventory.models import BatchLot, StockBalance, StockMovement, Warehouse
from inventory.services import InventoryService
from tests.conftest import make_product

pytestmark = pytest.mark.django_db

URL = "/api/v1/inventory/alerts/expiry/"


def _expired_lot(tenant, sku, qty="10"):
    product = make_product(tenant.company, sku=sku, name=sku, track_batch=True, purchase_price="30")
    InventoryService.post_opening(
        company=tenant.company, product=product, quantity=Decimal(qty), unit_cost=Decimal("20"),
        batch_no=f"{sku}-L1", expiry_date=date.today() + timedelta(days=30), user=tenant.owner,
    )
    balance = StockBalance.objects.get(company=tenant.company, product=product)
    BatchLot.objects.filter(pk=balance.batch_id).update(expiry_date=date.today() - timedelta(days=3))
    return product, balance


def _body(balance, qty, **extra):
    return {
        "product": balance.product_id, "warehouse": balance.warehouse_id, "batch": balance.batch_id,
        "quantity": qty, "reason": "EXPIRED", **extra,
    }


def _moves(tenant, product):
    return StockMovement.objects.filter(company=tenant.company, product=product, reference_type="expiry_write_off")


def test_a_repeated_write_off_with_the_same_key_posts_once(tenant_a):
    product, balance = _expired_lot(tenant_a, "IDR6-1")
    first = tenant_a.client.post(URL, _body(balance, "4"), format="json", HTTP_IDEMPOTENCY_KEY="idr6-k1")
    second = tenant_a.client.post(URL, _body(balance, "4"), format="json", HTTP_IDEMPOTENCY_KEY="idr6-k1")
    assert first.status_code == second.status_code == 201, (first.data, second.data)
    assert _moves(tenant_a, product).count() == 1
    assert StockBalance.objects.get(pk=balance.pk).on_hand == Decimal("6")


def test_a_second_write_off_with_a_new_key_is_capped_by_what_is_left(tenant_a):
    product, balance = _expired_lot(tenant_a, "IDR6-2")
    assert tenant_a.client.post(URL, _body(balance, "10"), format="json", HTTP_IDEMPOTENCY_KEY="idr6-a").status_code == 201
    again = tenant_a.client.post(URL, _body(balance, "10"), format="json", HTTP_IDEMPOTENCY_KEY="idr6-b")
    assert again.status_code == 400
    assert _moves(tenant_a, product).count() == 1


@pytest.mark.parametrize("quantity", ["abc", "NaN", "Infinity", "-3", "0", ""])
def test_a_bad_quantity_is_a_message_not_a_server_error(tenant_a, quantity):
    product, balance = _expired_lot(tenant_a, "IDR6-3")
    resp = tenant_a.client.post(URL, _body(balance, quantity), format="json")
    assert resp.status_code == 400, resp.data
    assert _moves(tenant_a, product).count() == 0


@pytest.mark.parametrize("params", [{"days": "soon"}, {"warehouse": "north"}])
def test_bad_filters_on_the_list_are_a_message_not_a_server_error(tenant_a, params):
    resp = tenant_a.client.get(URL, params)
    assert resp.status_code == 400, resp.data


def test_a_write_off_can_be_dated_in_the_past_but_not_the_future(tenant_a):
    product, balance = _expired_lot(tenant_a, "IDR6-4")
    past = (date.today() - timedelta(days=2)).isoformat()
    ok = tenant_a.client.post(URL, _body(balance, "2", movement_date=past), format="json")
    assert ok.status_code == 201, ok.data
    assert _moves(tenant_a, product).get().movement_date.isoformat() == past
    future = (date.today() + timedelta(days=2)).isoformat()
    assert tenant_a.client.post(URL, _body(balance, "2", movement_date=future), format="json").status_code == 400
    assert tenant_a.client.post(URL, _body(balance, "2", movement_date="yesterday"), format="json").status_code == 400
    assert _moves(tenant_a, product).count() == 1


def test_lots_in_the_system_in_transit_godown_are_not_listed(tenant_a):
    product, balance = _expired_lot(tenant_a, "IDR6-5")
    transit = Warehouse.objects.create(company=tenant_a.company, name="In transit", code="TRANSIT", is_system=True)
    StockBalance.objects.create(
        company=tenant_a.company, warehouse=transit, product=product, batch_id=balance.batch_id,
        on_hand=Decimal("5"), reserved=Decimal("0"),
    )
    items = tenant_a.client.get(URL, {"days": 30}).data["items"]
    assert {row["warehouse"] for row in items} == {balance.warehouse_id}


def test_a_lot_carries_the_bill_it_came_in_on(tenant_a):
    from inventory.models import MovementType

    product, balance = _expired_lot(tenant_a, "IDR6-6")
    InventoryService.post_movement(
        company=tenant_a.company, product=product, movement_type=MovementType.PURCHASE, quantity=Decimal("1"),
        unit_cost=Decimal("20"), user=tenant_a.owner, warehouse=balance.warehouse,
        batch=BatchLot.objects.get(pk=balance.batch_id), reference_type="purchase_invoice", reference_id="77",
    )
    rows = tenant_a.client.get(URL, {"days": 30}).data["items"]
    assert [row["purchase_invoice"] for row in rows if row["product"] == product.id] == [77]


def test_a_lot_with_no_traceable_bill_has_none(tenant_a):
    product, _balance = _expired_lot(tenant_a, "IDR6-7")
    rows = tenant_a.client.get(URL, {"days": 30}).data["items"]
    assert [row["purchase_invoice"] for row in rows if row["product"] == product.id] == [None]
