"""INV-IDR-01 — a refused stock write must not poison its Idempotency-Key, and a transfer
draft is created once per key."""

from __future__ import annotations

from decimal import Decimal

import pytest

from inventory.models import StockBalance, StockMovement, StockTransfer, Warehouse
from tests.conftest import add_stock, make_product

pytestmark = pytest.mark.django_db

ADJ = "/api/v1/inventory/adjustments/"
TRANSFERS = "/api/v1/inventory/transfers/"


def _post(client, url, body, key):
    return client.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY=key)


def _restock(tenant, product, qty):
    """More stock after the opening balance (a second opening-stock post is refused)."""
    from inventory.models import MovementType
    from inventory.services import InventoryService

    return InventoryService.post_movement(
        company=tenant.company, product=product, movement_type=MovementType.ADJUSTMENT,
        quantity=Decimal(qty), unit_cost=Decimal("80"), user=tenant.owner,
    )


def _block_negative_stock(company):
    company.negative_stock_policy = "BLOCK"
    company.save(update_fields=["negative_stock_policy"])


def test_refused_adjustment_can_be_retried_with_the_same_key_once_stock_is_added(tenant_a):
    _block_negative_stock(tenant_a.company)
    product = make_product(tenant_a.company, sku="IDR1-A")
    add_stock(tenant_a, product, "2")
    body = {"product": product.id, "quantity": "-5", "reason": "Damaged"}

    refused = _post(tenant_a.client, ADJ, body, "idr1-adj-1")
    assert refused.status_code == 400, refused.data
    assert StockMovement.objects.filter(
        company=tenant_a.company, product=product, reference_type="manual_adjustment"
    ).count() == 0

    _restock(tenant_a, product, "10")
    retried = _post(tenant_a.client, ADJ, body, "idr1-adj-1")
    assert retried.status_code == 201, retried.data
    assert StockBalance.objects.get(company=tenant_a.company, product=product).on_hand == Decimal("7")


def test_refused_adjustment_can_be_corrected_and_resent_with_the_same_key(tenant_a):
    """The old behaviour answered 422 'key reused' here; the refusal is released instead."""
    _block_negative_stock(tenant_a.company)
    product = make_product(tenant_a.company, sku="IDR1-B")
    add_stock(tenant_a, product, "2")

    assert _post(tenant_a.client, ADJ, {"product": product.id, "quantity": "-5", "reason": "Damaged"}, "idr1-adj-2").status_code == 400
    fixed = _post(tenant_a.client, ADJ, {"product": product.id, "quantity": "-1", "reason": "Damaged"}, "idr1-adj-2")
    assert fixed.status_code == 201, fixed.data
    assert StockBalance.objects.get(company=tenant_a.company, product=product).on_hand == Decimal("1")


def test_a_successful_adjustment_is_still_replayed_not_posted_twice(tenant_a):
    product = make_product(tenant_a.company, sku="IDR1-C")
    add_stock(tenant_a, product, "10")
    body = {"product": product.id, "quantity": "-2", "reason": "Damaged"}
    first = _post(tenant_a.client, ADJ, body, "idr1-adj-3")
    second = _post(tenant_a.client, ADJ, body, "idr1-adj-3")
    assert first.status_code == second.status_code == 201
    assert second.data["id"] == first.data["id"]
    assert StockBalance.objects.get(company=tenant_a.company, product=product).on_hand == Decimal("8")


def _two_godowns(tenant):
    main = Warehouse.objects.filter(company=tenant.company, is_system=False).order_by("id").first()
    if main is None:
        from inventory.services import InventoryService

        main = InventoryService.default_warehouse(tenant.company)
    other = Warehouse.objects.create(company=tenant.company, name="North", code="NORTH")
    return main, other


def _transfer_body(main, other, product, qty="1"):
    return {
        "from_warehouse": main.id, "to_warehouse": other.id,
        "lines": [{"product": product.id, "quantity": qty}],
    }


def test_transfer_draft_is_created_once_per_key(tenant_a):
    product = make_product(tenant_a.company, sku="IDR1-T1")
    add_stock(tenant_a, product, "10")
    main, other = _two_godowns(tenant_a)
    body = _transfer_body(main, other, product)

    first = _post(tenant_a.client, TRANSFERS, body, "idr1-tr-1")
    second = _post(tenant_a.client, TRANSFERS, body, "idr1-tr-1")
    assert first.status_code == 201, first.data
    assert second.status_code == 201, second.data
    assert second.data["id"] == first.data["id"]
    assert StockTransfer.objects.filter(company=tenant_a.company).count() == 1


def test_transfer_drafts_with_different_keys_are_separate(tenant_a):
    product = make_product(tenant_a.company, sku="IDR1-T2")
    add_stock(tenant_a, product, "10")
    main, other = _two_godowns(tenant_a)
    body = _transfer_body(main, other, product)
    assert _post(tenant_a.client, TRANSFERS, body, "idr1-tr-a").status_code == 201
    assert _post(tenant_a.client, TRANSFERS, body, "idr1-tr-b").status_code == 201
    assert StockTransfer.objects.filter(company=tenant_a.company).count() == 2


def test_refused_transfer_create_releases_its_key(tenant_a):
    product = make_product(tenant_a.company, sku="IDR1-T3")
    add_stock(tenant_a, product, "10")
    main, other = _two_godowns(tenant_a)
    bad = {"from_warehouse": main.id, "to_warehouse": main.id, "lines": [{"product": product.id, "quantity": "1"}]}
    assert _post(tenant_a.client, TRANSFERS, bad, "idr1-tr-c").status_code == 400
    good = _post(tenant_a.client, TRANSFERS, _transfer_body(main, other, product), "idr1-tr-c")
    assert good.status_code == 201, good.data


def test_dispatch_refused_for_stock_can_be_retried_with_the_same_key_after_restocking(tenant_a):
    _block_negative_stock(tenant_a.company)
    product = make_product(tenant_a.company, sku="IDR1-T4")
    add_stock(tenant_a, product, "5")
    main, other = _two_godowns(tenant_a)
    created = _post(tenant_a.client, TRANSFERS, _transfer_body(main, other, product, qty="8"), "idr1-tr-d")
    assert created.status_code == 201, created.data
    url = f"{TRANSFERS}{created.data['id']}/complete/"

    refused = tenant_a.client.post(url, {}, format="json", HTTP_IDEMPOTENCY_KEY="idr1-disp-1")
    assert refused.status_code == 400, refused.data

    _restock(tenant_a, product, "10")
    retried = tenant_a.client.post(url, {}, format="json", HTTP_IDEMPOTENCY_KEY="idr1-disp-1")
    assert retried.status_code == 200, retried.data
    assert StockTransfer.objects.get(pk=created.data["id"]).status == StockTransfer.Status.DISPATCHED
