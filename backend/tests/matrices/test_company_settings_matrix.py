"""Company behaviour-settings matrix (FG-2 settings matrix).

Run the core sale flow under each value of a behaviour setting and assert the
setting actually changes behaviour AND the invariant sweep stays clean in every
combination.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.invariants import assert_all_invariants
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("policy", ["BLOCK", "WARN"])
def test_negative_stock_policy(tenant_a, policy):
    company = tenant_a.company
    company.negative_stock_policy = policy
    company.save(update_fields=["negative_stock_policy"])

    product = make_product(company, gst_rate="18")
    add_stock(tenant_a, product, "2", unit_cost="50")
    customer = make_customer(company, gstin="29AAAAA0000A1ZY")
    inv = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "5", "unit_price": "100.00", "gst_rate": "18"}],
    )
    r = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")

    from inventory.services import InventoryService

    on_hand = InventoryService.available_quantity(company=company, product=product)
    if policy == "BLOCK":
        assert 400 <= r.status_code < 500, r.data
        assert on_hand == Decimal("2.000")
    else:  # WARN — oversell is allowed, stock goes negative
        assert r.status_code == 200, r.data
        assert on_hand == Decimal("-3.000")

    # invariants hold either way — no_negative_balance_when_blocked only fires under BLOCK
    assert_all_invariants(company)


@pytest.mark.parametrize("block_expired", [True, False])
def test_block_expired_stock(tenant_a, block_expired):
    company = tenant_a.company
    company.block_expired_stock = block_expired
    company.save(update_fields=["block_expired_stock"])

    from datetime import date

    from inventory.models import BatchLot, MovementType
    from inventory.services import InventoryService

    product = make_product(company, gst_rate="18", track_batch=True)
    batch = BatchLot.objects.create(
        company=company, product=product, batch_no="OLD", expiry_date=date(2020, 1, 1)
    )
    InventoryService.post_movement(
        company=company, product=product, movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("10"), unit_cost=Decimal("50"), user=tenant_a.owner, batch=batch,
    )

    def _issue():
        return InventoryService.post_movement(
            company=company, product=product, movement_type=MovementType.SALE,
            quantity=Decimal("1"), user=tenant_a.owner, batch=batch,
        )

    if block_expired:
        with pytest.raises(Exception):
            _issue()
    else:
        _issue()  # allowed
    assert_all_invariants(company)
