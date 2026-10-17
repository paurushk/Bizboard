"""INV-IDR-02 - one stock-loss path: approval parity, server-enforced recheck, approve-then-apply."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import CompanyUser, User
from inventory.models import BatchLot, SerialNumber, StockBalance, StockCountSession, StockMovement
from inventory.services import InventoryService
from tests.conftest import add_stock, make_product

pytestmark = pytest.mark.django_db

EXPIRY = "/api/v1/inventory/alerts/expiry/"
ADJ = "/api/v1/inventory/adjustments/"
COUNTS = "/api/v1/inventory/stock-counts/"
FLAG = "STOCK_LOSS_APPROVAL_ALL_PATHS"


def _manager(tenant, email="mgr-idr02@alpha.test"):
    """A second person who can run stock but cannot approve (only an owner decides)."""
    user = User.objects.create_user(email=email, password="StrongPass123!")
    CompanyUser.objects.create(
        company=tenant.company, user=user, role=CompanyUser.Role.MANAGER, can_manage_inventory=True,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return user, client


def _flag_on(tenant):
    tenant.company.feature_flags = {**(tenant.company.feature_flags or {}), FLAG: True}
    tenant.company.save(update_fields=["feature_flags"])


def _lot(tenant, sku, *, qty="100", cost="200", price="200"):
    product = make_product(tenant.company, sku=sku, name=sku, track_batch=True, purchase_price=price)
    InventoryService.post_opening(
        company=tenant.company, product=product, quantity=Decimal(qty), unit_cost=Decimal(cost),
        batch_no=f"{sku}-L1", expiry_date=date.today() + timedelta(days=30), user=tenant.owner,
    )
    balance = StockBalance.objects.get(company=tenant.company, product=product)
    BatchLot.objects.filter(pk=balance.batch_id).update(expiry_date=date.today() - timedelta(days=2))
    return product, balance


def _write_off(client, balance, qty):
    return client.post(
        EXPIRY,
        {"product": balance.product_id, "warehouse": balance.warehouse_id, "batch": balance.batch_id,
         "quantity": str(qty), "reason": "EXPIRED"},
        format="json",
    )


def _decide(owner_client, approval_id, accept=True):
    return owner_client.post(f"/api/v1/plan/approvals/{approval_id}/decide/", {"accept": accept}, format="json")


def _data(resp):
    return resp.data.get("data", resp.data)


def _loss_moves(tenant, product, source):
    return StockMovement.objects.filter(company=tenant.company, product=product, reference_type=source)


# ---- expiry write-off ------------------------------------------------------------------------

def test_expiry_write_off_is_unchanged_while_the_flag_is_off(tenant_a):
    _user, manager = _manager(tenant_a)
    product, balance = _lot(tenant_a, "IDR2-E1")
    resp = _write_off(manager, balance, 50)  # 50 x 200 = 10,000
    assert resp.status_code == 201, resp.data
    assert resp.data["status"] == "APPLIED"
    assert _loss_moves(tenant_a, product, "expiry_write_off").count() == 1


def test_large_expiry_write_off_waits_for_the_owner_when_the_flag_is_on(tenant_a):
    _flag_on(tenant_a)
    _user, manager = _manager(tenant_a)
    product, balance = _lot(tenant_a, "IDR2-E2")
    resp = _write_off(manager, balance, 50)
    assert resp.status_code == 202, resp.data
    assert resp.data["status"] == "PENDING" and resp.data["approval_id"]
    assert _loss_moves(tenant_a, product, "expiry_write_off").count() == 0
    assert StockBalance.objects.get(pk=balance.pk).on_hand == Decimal("100")


def test_owner_approval_applies_the_write_off_for_the_requester(tenant_a):
    _flag_on(tenant_a)
    _user, manager = _manager(tenant_a)
    product, balance = _lot(tenant_a, "IDR2-E3")
    pending = _write_off(manager, balance, 50)
    decided = _decide(tenant_a.client, pending.data["approval_id"])
    assert decided.status_code == 200, decided.data
    body = _data(decided)
    assert body["status"] == "APPROVED"
    assert body["applied"] is True
    assert _loss_moves(tenant_a, product, "expiry_write_off").count() == 1
    assert StockBalance.objects.get(pk=balance.pk).on_hand == Decimal("50")
    # Deciding again must not write it off twice.
    again = _decide(tenant_a.client, pending.data["approval_id"])
    assert again.status_code == 400
    assert _loss_moves(tenant_a, product, "expiry_write_off").count() == 1


def test_rejected_write_off_never_moves_stock(tenant_a):
    _flag_on(tenant_a)
    _user, manager = _manager(tenant_a)
    product, balance = _lot(tenant_a, "IDR2-E4")
    pending = _write_off(manager, balance, 50)
    _decide(tenant_a.client, pending.data["approval_id"], accept=False)
    assert _loss_moves(tenant_a, product, "expiry_write_off").count() == 0
    # Repeating the action raises a fresh request, it does not reuse the rejected one.
    assert _write_off(manager, balance, 50).status_code == 202


def test_small_write_off_needs_no_approval_even_with_the_flag_on(tenant_a):
    _flag_on(tenant_a)
    _user, manager = _manager(tenant_a)
    product, balance = _lot(tenant_a, "IDR2-E5", qty="1000", cost="10", price="10")
    resp = _write_off(manager, balance, 1)  # Rs 10, 0.1 %
    assert resp.status_code == 201, resp.data


def test_sole_owner_is_not_blocked_by_the_flag(tenant_a):
    _flag_on(tenant_a)
    product, balance = _lot(tenant_a, "IDR2-E6")
    resp = _write_off(tenant_a.client, balance, 50)
    assert resp.status_code == 201, resp.data


# ---- manual adjustment (the reference path) --------------------------------------------------

def test_approved_adjustment_is_applied_without_the_requester_coming_back(tenant_a):
    _user, manager = _manager(tenant_a)
    product = make_product(tenant_a.company, sku="IDR2-A1", purchase_price="500")
    add_stock(tenant_a, product, "100", unit_cost="500")
    pending = manager.post(ADJ, {"product": product.id, "quantity": "-30", "reason": "Damaged"}, format="json")
    assert pending.status_code == 202, pending.data
    assert StockBalance.objects.get(company=tenant_a.company, product=product).on_hand == Decimal("100")
    decided = _decide(tenant_a.client, pending.data["approval_id"])
    assert decided.status_code == 200, decided.data
    assert _data(decided)["applied"] is True
    assert StockBalance.objects.get(company=tenant_a.company, product=product).on_hand == Decimal("70")
    assert _loss_moves(tenant_a, product, "manual_adjustment").count() == 1


def test_adjustment_value_uses_the_valuation_cost_when_the_price_was_never_set(tenant_a):
    _user, manager = _manager(tenant_a)
    product = make_product(tenant_a.company, sku="IDR2-A2", purchase_price="0")
    add_stock(tenant_a, product, "1000", unit_cost="500")
    # 5 units = Rs 2,500 and 0.5 % of stock: below both limits, so it posts.
    assert manager.post(ADJ, {"product": product.id, "quantity": "-5", "reason": "x"}, format="json").status_code == 201
    # 25 units = Rs 12,500 at the valuation cost, though the item master price is 0.
    big = manager.post(ADJ, {"product": product.id, "quantity": "-25", "reason": "x"}, format="json")
    assert big.status_code == 202, big.data


# ---- serial scrap ----------------------------------------------------------------------------

def test_scrap_of_a_valuable_serial_waits_for_approval_when_the_flag_is_on(tenant_a):
    _flag_on(tenant_a)
    _user, manager = _manager(tenant_a)
    product = make_product(tenant_a.company, sku="IDR2-S1", track_serial=True, purchase_price="20000")
    InventoryService.post_opening(
        company=tenant_a.company, product=product, quantity=Decimal("2"), unit_cost=Decimal("20000"),
        serial_numbers=["SN-1", "SN-2"], user=tenant_a.owner,
    )
    serial = SerialNumber.objects.get(company=tenant_a.company, serial_number="SN-1")
    resp = manager.post(f"/api/v1/inventory/serials/{serial.pk}/transition/", {"status": "SCRAPPED"}, format="json")
    assert resp.status_code == 202, resp.data
    serial.refresh_from_db()
    assert serial.status == SerialNumber.Status.AVAILABLE
    assert _loss_moves(tenant_a, product, "serial_scrap").count() == 0


# ---- stock count -----------------------------------------------------------------------------

def _count(client, tenant, product, counted):
    warehouse_id = StockBalance.objects.get(company=tenant.company, product=product).warehouse_id
    created = client.post(COUNTS, {"warehouse": warehouse_id}, format="json")
    assert created.status_code == 201, created.data
    sid = created.data["id"]
    lines = [
        {"id": row["id"], "counted_qty": str(counted if row["product"] == product.id else row["system_qty"])}
        for row in created.data["lines"]
    ]
    assert client.patch(f"{COUNTS}{sid}/", {"lines": lines}, format="json").status_code == 200
    line_id = next(row["id"] for row in created.data["lines"] if row["product"] == product.id)
    return sid, line_id


def test_count_post_refuses_a_large_difference_that_was_not_rechecked(tenant_a):
    product = make_product(tenant_a.company, sku="IDR2-C1", purchase_price="10")
    add_stock(tenant_a, product, "100", unit_cost="10")
    sid, line_id = _count(tenant_a.client, tenant_a, product, 80)  # 20 units, above the 5-unit limit
    refused = tenant_a.client.post(f"{COUNTS}{sid}/post/", {}, format="json")
    assert refused.status_code == 400, refused.data
    assert "recheck" in str(refused.data).lower()
    assert _loss_moves(tenant_a, product, "stock_count").count() == 0
    ok = tenant_a.client.post(f"{COUNTS}{sid}/post/", {"rechecked_line_ids": [line_id]}, format="json")
    assert ok.status_code == 200, ok.data
    assert StockBalance.objects.get(company=tenant_a.company, product=product).on_hand == Decimal("80")


def test_small_count_difference_needs_no_recheck(tenant_a):
    product = make_product(tenant_a.company, sku="IDR2-C2", purchase_price="10")
    add_stock(tenant_a, product, "100", unit_cost="10")
    sid, _line = _count(tenant_a.client, tenant_a, product, 98)
    assert tenant_a.client.post(f"{COUNTS}{sid}/post/", {}, format="json").status_code == 200


def test_a_costly_count_waits_for_the_owner_when_the_flag_is_on_then_posts_once(tenant_a):
    _flag_on(tenant_a)
    _user, manager = _manager(tenant_a)
    product = make_product(tenant_a.company, sku="IDR2-C3", purchase_price="1000")
    add_stock(tenant_a, product, "100", unit_cost="1000")
    sid, line_id = _count(manager, tenant_a, product, 90)
    body = {"rechecked_line_ids": [line_id]}
    pending = manager.post(f"{COUNTS}{sid}/post/", body, format="json")
    assert pending.status_code == 202, pending.data
    assert StockCountSession.objects.get(pk=sid).status == StockCountSession.Status.COUNTED
    assert _loss_moves(tenant_a, product, "stock_count").count() == 0

    assert _decide(tenant_a.client, pending.data["approval_id"]).status_code == 200
    posted = manager.post(f"{COUNTS}{sid}/post/", body, format="json")
    assert posted.status_code == 200, posted.data
    assert _loss_moves(tenant_a, product, "stock_count").count() == 1
    assert StockBalance.objects.get(company=tenant_a.company, product=product).on_hand == Decimal("90")


def test_count_gain_is_never_held_for_approval(tenant_a):
    _flag_on(tenant_a)
    _user, manager = _manager(tenant_a)
    product = make_product(tenant_a.company, sku="IDR2-C4", purchase_price="1000")
    add_stock(tenant_a, product, "100", unit_cost="1000")
    sid, line_id = _count(manager, tenant_a, product, 110)
    done = manager.post(f"{COUNTS}{sid}/post/", {"rechecked_line_ids": [line_id]}, format="json")
    assert done.status_code == 200, done.data


def test_no_screen_posts_a_stock_loss_movement_outside_the_shared_service():
    """Every stock-loss path goes through inventory/stock_loss.py (the one place with the approval rule)."""
    import pathlib

    views = (pathlib.Path(__file__).resolve().parent.parent / "inventory" / "views.py").read_text(encoding="utf-8")
    assert "MovementType.ADJUSTMENT" not in views
    for source in ("expiry_write_off", "serial_scrap", "manual_adjustment"):
        assert f'reference_type="{source}"' not in views
