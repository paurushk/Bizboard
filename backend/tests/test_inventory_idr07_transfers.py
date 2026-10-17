"""INV-IDR-07 - a transfer shortage is a claim that can be settled, and the list can be narrowed."""

from __future__ import annotations

from decimal import Decimal

import pytest

from inventory.models import StockBalance, StockMovement, Warehouse
from inventory.services import InventoryService, StockTransferService
from tests.conftest import add_stock, make_product
from tests.test_inventory_transfers_wp05 import _custodian, _draft, _on_hand

pytestmark = pytest.mark.django_db

TRANSFERS = "/api/v1/inventory/transfers/"


@pytest.fixture
def godowns(tenant_a):
    main = InventoryService.default_warehouse(tenant_a.company)
    north = Warehouse.objects.create(company=tenant_a.company, name="North", code="NR7")
    return main, north


def _short_transfer(tenant, main, north, sku, sent="5", got="3"):
    product = make_product(tenant.company, sku=sku)
    add_stock(tenant, product, "10")
    data = _draft(tenant.client, product, main, north, qty=sent)
    tenant.client.post(f"{TRANSFERS}{data['id']}/complete/", {}, format="json")
    line_id = data["lines"][0]["id"]
    done = tenant.client.post(
        f"{TRANSFERS}{data['id']}/receive/",
        {"receipts": [{"line": line_id, "quantity": got, "reason": "Broken"}]}, format="json",
    )
    assert done.status_code == 200, done.data
    return product, data["id"], line_id


def _transit(tenant):
    return StockTransferService.in_transit_warehouse(tenant.company)


def test_dispatch_stamps_the_time_so_the_page_can_show_age(tenant_a, godowns):
    main, north = godowns
    product = make_product(tenant_a.company, sku="I7-1")
    add_stock(tenant_a, product, "10")
    data = _draft(tenant_a.client, product, main, north)
    assert data["dispatched_at"] is None
    sent = tenant_a.client.post(f"{TRANSFERS}{data['id']}/complete/", {}, format="json")
    assert sent.data["dispatched_at"]


def test_write_off_clears_the_claim_and_books_a_loss(tenant_a, godowns):
    main, north = godowns
    product, tid, line_id = _short_transfer(tenant_a, main, north, "I7-2")
    assert _on_hand(tenant_a.company, product, _transit(tenant_a)) == Decimal("2")

    resp = tenant_a.client.post(
        f"{TRANSFERS}{tid}/resolve-shortage/", {"resolutions": [{"line": line_id, "action": "WRITE_OFF"}]},
        format="json", HTTP_IDEMPOTENCY_KEY="i7-wo-1",
    )
    assert resp.status_code == 200, resp.data
    assert resp.data["lines"][0]["shortage_resolution"] == "WRITE_OFF"
    assert _on_hand(tenant_a.company, product, _transit(tenant_a)) == Decimal("0")
    assert _on_hand(tenant_a.company, product, main) == Decimal("5")
    assert StockMovement.objects.filter(
        company=tenant_a.company, reference_type="transfer_shortage", quantity=Decimal("-2"),
    ).exists()


def test_return_puts_the_short_quantity_back_in_the_source_godown(tenant_a, godowns):
    main, north = godowns
    product, tid, line_id = _short_transfer(tenant_a, main, north, "I7-3")
    resp = tenant_a.client.post(
        f"{TRANSFERS}{tid}/resolve-shortage/", {"resolutions": [{"line": line_id, "action": "RETURN"}]},
        format="json", HTTP_IDEMPOTENCY_KEY="i7-ret-1",
    )
    assert resp.status_code == 200, resp.data
    assert _on_hand(tenant_a.company, product, main) == Decimal("7")
    assert _on_hand(tenant_a.company, product, _transit(tenant_a)) == Decimal("0")
    assert _on_hand(tenant_a.company, product, north) == Decimal("3")


def test_a_shortage_can_only_be_settled_once(tenant_a, godowns):
    main, north = godowns
    _product, tid, line_id = _short_transfer(tenant_a, main, north, "I7-4")
    body = {"resolutions": [{"line": line_id, "action": "WRITE_OFF"}]}
    assert tenant_a.client.post(f"{TRANSFERS}{tid}/resolve-shortage/", body, format="json").status_code == 200
    again = tenant_a.client.post(f"{TRANSFERS}{tid}/resolve-shortage/", body, format="json")
    assert again.status_code == 400


def test_a_line_without_a_shortage_cannot_be_settled(tenant_a, godowns):
    main, north = godowns
    _product, tid, line_id = _short_transfer(tenant_a, main, north, "I7-5", sent="4", got="4")
    resp = tenant_a.client.post(
        f"{TRANSFERS}{tid}/resolve-shortage/", {"resolutions": [{"line": line_id, "action": "WRITE_OFF"}]},
        format="json",
    )
    assert resp.status_code == 400


def test_only_owner_or_manager_settles_a_shortage(tenant_a, godowns):
    main, north = godowns
    _product, tid, line_id = _short_transfer(tenant_a, main, north, "I7-6")
    resp = _custodian(tenant_a).post(
        f"{TRANSFERS}{tid}/resolve-shortage/", {"resolutions": [{"line": line_id, "action": "WRITE_OFF"}]},
        format="json",
    )
    assert resp.status_code == 403


def test_cancel_after_settling_does_not_clear_the_short_quantity_twice(tenant_a, godowns):
    main, north = godowns
    product, tid, line_id = _short_transfer(tenant_a, main, north, "I7-7")
    tenant_a.client.post(
        f"{TRANSFERS}{tid}/resolve-shortage/", {"resolutions": [{"line": line_id, "action": "RETURN"}]},
        format="json",
    )
    cancelled = tenant_a.client.post(f"{TRANSFERS}{tid}/cancel/", {}, format="json")
    assert cancelled.status_code == 200, cancelled.data
    assert _on_hand(tenant_a.company, product, _transit(tenant_a)) == Decimal("0")
    assert StockBalance.objects.get(company=tenant_a.company, product=product, warehouse=main).on_hand == Decimal("10")


def test_list_filters_by_status_search_and_open_shortage(tenant_a, godowns):
    main, north = godowns
    _p1, short_id, _l = _short_transfer(tenant_a, main, north, "I7-8")
    _p2, clean_id, _l2 = _short_transfer(tenant_a, main, north, "I7-9", sent="2", got="2")
    draft = make_product(tenant_a.company, sku="I7-10", name="Zinc Paste")
    add_stock(tenant_a, draft, "5")
    draft_id = _draft(tenant_a.client, draft, main, north, qty="1")["id"]

    def ids(query):
        data = tenant_a.client.get(f"{TRANSFERS}?{query}").data
        rows = data["results"] if isinstance(data, dict) and "results" in data else data
        return {row["id"] for row in rows}

    assert ids("status=DRAFT") == {draft_id}
    assert ids("open_shortage=1") == {short_id}
    assert ids("q=Zinc") == {draft_id}
    assert {short_id, clean_id, draft_id} <= ids(f"warehouse={north.id}")
