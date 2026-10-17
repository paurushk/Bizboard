"""INV-WP-01 — stock adjustment endpoint (inventory review #1, retry safety, zero quantity)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from inventory.models import StockBalance, StockMovement
from tests.conftest import add_stock, make_product

pytestmark = pytest.mark.django_db

URL = "/api/v1/inventory/adjustments/"


def _post(client, body, key=None):
    extra = {"HTTP_IDEMPOTENCY_KEY": key} if key else {}
    return client.post(URL, body, format="json", **extra)


def test_applied_adjustment_says_so(tenant_a):
    product = make_product(tenant_a.company, sku="ADJ-OK")
    add_stock(tenant_a, product, "10")
    resp = _post(tenant_a.client, {"product": product.id, "quantity": "-3", "reason": "Damaged"})
    assert resp.status_code == 201, resp.data
    assert resp.data["status"] == "APPLIED"
    balance = StockBalance.objects.get(company=tenant_a.company, product=product)
    assert balance.on_hand == Decimal("7")


def test_retry_with_same_key_posts_one_movement(tenant_a):
    product = make_product(tenant_a.company, sku="ADJ-RETRY")
    add_stock(tenant_a, product, "10")
    body = {"product": product.id, "quantity": "-2", "reason": "Damaged"}
    first = _post(tenant_a.client, body, key="adj-key-1")
    second = _post(tenant_a.client, body, key="adj-key-1")
    assert first.status_code == 201, first.data
    assert second.status_code == 201, second.data
    assert second.data["id"] == first.data["id"]
    moves = StockMovement.objects.filter(company=tenant_a.company, product=product, reference_type="manual_adjustment")
    assert moves.count() == 1
    assert StockBalance.objects.get(company=tenant_a.company, product=product).on_hand == Decimal("8")


def test_different_keys_post_separate_movements(tenant_a):
    product = make_product(tenant_a.company, sku="ADJ-TWO")
    add_stock(tenant_a, product, "10")
    body = {"product": product.id, "quantity": "-1", "reason": "Damaged"}
    assert _post(tenant_a.client, body, key="k-a").status_code == 201
    assert _post(tenant_a.client, body, key="k-b").status_code == 201
    assert StockBalance.objects.get(company=tenant_a.company, product=product).on_hand == Decimal("8")


def test_zero_quantity_is_rejected(tenant_a):
    product = make_product(tenant_a.company, sku="ADJ-ZERO")
    add_stock(tenant_a, product, "10")
    resp = _post(tenant_a.client, {"product": product.id, "quantity": "0", "reason": "Damaged"})
    assert resp.status_code == 400, resp.data


def test_fractional_quantity_is_accepted(tenant_a):
    product = make_product(tenant_a.company, sku="ADJ-FRAC")
    add_stock(tenant_a, product, "10")
    resp = _post(tenant_a.client, {"product": product.id, "quantity": "-0.5", "reason": "Spillage"})
    assert resp.status_code == 201, resp.data
    assert StockBalance.objects.get(company=tenant_a.company, product=product).on_hand == Decimal("9.5")


def test_pending_approval_response_is_unchanged(tenant_a):
    from accounts.models import CompanyUser, User

    second = User.objects.create_user(email="second-owner-wp01@alpha.test", password="StrongPass123!")
    CompanyUser.objects.create(company=tenant_a.company, user=second, role=CompanyUser.Role.OWNER)
    product = make_product(tenant_a.company, sku="ADJ-PEND", purchase_price="10000")
    resp = _post(tenant_a.client, {"product": product.id, "quantity": "1", "reason": "found"})
    assert resp.status_code == 202, resp.data
    assert resp.data["status"] == "PENDING"
    assert resp.data["approval_id"]
    assert not StockMovement.objects.filter(
        company=tenant_a.company, product=product, reference_type="manual_adjustment"
    ).exists()


def test_adjustment_keeps_a_reason_code_and_the_ledger_can_filter_on_it(tenant_a):
    product = make_product(tenant_a.company, sku="RC-1")
    add_stock(tenant_a, product, "10")
    resp = tenant_a.client.post(
        "/api/v1/inventory/adjustments/",
        {"product": product.id, "quantity": "-2", "reason": "Dropped crate", "reason_code": "DAMAGED"},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert resp.data["reason_code"] == "DAMAGED"
    rows = tenant_a.client.get("/api/v1/inventory/movements/", {"reason_code": "DAMAGED"}).data
    rows = rows["results"] if isinstance(rows, dict) else rows
    assert [r["reason"] for r in rows] == ["Dropped crate"]
    bad = tenant_a.client.post(
        "/api/v1/inventory/adjustments/",
        {"product": product.id, "quantity": "-1", "reason": "x", "reason_code": "NOPE"},
        format="json",
    )
    assert bad.status_code == 400
