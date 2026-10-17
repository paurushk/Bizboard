"""INV-WP-05 — stock transfer lifecycle the UI now exposes (inventory review #8, #9)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import CompanyUser, User
from inventory.models import StockBalance, StockMovement, StockTransfer, Warehouse
from inventory.services import InventoryService
from tests.conftest import add_stock, make_product

pytestmark = pytest.mark.django_db

TRANSFERS = "/api/v1/inventory/transfers/"


@pytest.fixture
def godowns(tenant_a):
    main = InventoryService.default_warehouse(tenant_a.company)
    north = Warehouse.objects.create(company=tenant_a.company, name="North", code="NR")
    return main, north


def _on_hand(company, product, warehouse):
    row = StockBalance.objects.filter(company=company, product=product, warehouse=warehouse, batch__isnull=True).first()
    return row.on_hand if row else Decimal("0")


def _draft(client, product, main, north, qty="5"):
    resp = client.post(
        TRANSFERS,
        {
            "from_warehouse": main.id,
            "to_warehouse": north.id,
            "lines": [{"product": product.id, "quantity": qty}],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    return resp.data


def _custodian(tenant):
    user = User.objects.create_user(email="custodian-wp05@alpha.test", password="StrongPass123!")
    CompanyUser.objects.create(
        company=tenant.company, user=user, role=CompanyUser.Role.SALES_STAFF, can_manage_inventory=True,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_lines_name_the_product_and_zero_quantity_is_refused(tenant_a, godowns):
    main, north = godowns
    product = make_product(tenant_a.company, sku="TR-1", name="Soap")
    add_stock(tenant_a, product, "10")
    data = _draft(tenant_a.client, product, main, north)
    assert data["lines"][0]["product_name"] == "Soap"
    assert data["lines"][0]["shortage_qty"] in ("0.000", 0, "0")
    bad = tenant_a.client.post(
        TRANSFERS,
        {"from_warehouse": main.id, "to_warehouse": north.id, "lines": [{"product": product.id, "quantity": "0"}]},
        format="json",
    )
    assert bad.status_code == 400


def test_a_draft_can_be_cancelled_without_touching_stock(tenant_a, godowns):
    main, north = godowns
    product = make_product(tenant_a.company, sku="TR-2")
    add_stock(tenant_a, product, "10")
    data = _draft(tenant_a.client, product, main, north)
    resp = tenant_a.client.post(f"{TRANSFERS}{data['id']}/cancel/", {}, format="json")
    assert resp.status_code == 200, resp.data
    assert resp.data["status"] == "CANCELLED"
    assert not StockMovement.objects.filter(
        company=tenant_a.company, reference_type__startswith="stock_transfer"
    ).exists()
    assert _on_hand(tenant_a.company, product, main) == Decimal("10")


def test_a_dispatched_transfer_can_be_cancelled_and_stock_comes_back(tenant_a, godowns):
    main, north = godowns
    product = make_product(tenant_a.company, sku="TR-3")
    add_stock(tenant_a, product, "10")
    data = _draft(tenant_a.client, product, main, north, qty="4")
    sent = tenant_a.client.post(f"{TRANSFERS}{data['id']}/complete/", {}, format="json")
    assert sent.status_code == 200, sent.data
    assert sent.data["status"] == "DISPATCHED"
    assert _on_hand(tenant_a.company, product, main) == Decimal("6")
    resp = tenant_a.client.post(f"{TRANSFERS}{data['id']}/cancel/", {}, format="json")
    assert resp.status_code == 200, resp.data
    assert _on_hand(tenant_a.company, product, main) == Decimal("10")


def test_short_receipt_records_the_shortage_on_the_line(tenant_a, godowns):
    main, north = godowns
    product = make_product(tenant_a.company, sku="TR-4")
    add_stock(tenant_a, product, "10")
    data = _draft(tenant_a.client, product, main, north, qty="5")
    tenant_a.client.post(f"{TRANSFERS}{data['id']}/complete/", {}, format="json")
    line_id = data["lines"][0]["id"]
    resp = tenant_a.client.post(
        f"{TRANSFERS}{data['id']}/receive/",
        {"receipts": [{"line": line_id, "quantity": "3", "reason": "Two boxes broken"}]},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    assert resp.data["status"] == "COMPLETED"
    line = resp.data["lines"][0]
    assert Decimal(str(line["shortage_qty"])) == Decimal("2")
    assert line["shortage_reason"] == "Two boxes broken"
    assert _on_hand(tenant_a.company, product, north) == Decimal("3")


def test_only_an_owner_or_manager_can_cancel_a_received_transfer(tenant_a, godowns):
    main, north = godowns
    product = make_product(tenant_a.company, sku="TR-5")
    add_stock(tenant_a, product, "10")
    data = _draft(tenant_a.client, product, main, north, qty="2")
    tenant_a.client.post(f"{TRANSFERS}{data['id']}/complete/", {}, format="json")
    tenant_a.client.post(f"{TRANSFERS}{data['id']}/receive/", {}, format="json")
    assert StockTransfer.objects.get(pk=data["id"]).status == StockTransfer.Status.COMPLETED

    custodian = _custodian(tenant_a)
    refused = custodian.post(f"{TRANSFERS}{data['id']}/cancel/", {}, format="json")
    assert refused.status_code == 403
    assert StockTransfer.objects.get(pk=data["id"]).status == StockTransfer.Status.COMPLETED

    allowed = tenant_a.client.post(f"{TRANSFERS}{data['id']}/cancel/", {}, format="json")
    assert allowed.status_code == 200, allowed.data


def test_custodian_can_still_cancel_a_draft(tenant_a, godowns):
    main, north = godowns
    product = make_product(tenant_a.company, sku="TR-6")
    add_stock(tenant_a, product, "10")
    data = _draft(tenant_a.client, product, main, north)
    custodian = _custodian(tenant_a)
    assert custodian.post(f"{TRANSFERS}{data['id']}/cancel/", {}, format="json").status_code == 200


def test_batch_list_can_be_limited_to_lots_stocked_in_one_godown(tenant_a, godowns):
    main, north = godowns
    product = make_product(tenant_a.company, sku="TR-B", track_batch=True)
    InventoryService.post_opening(
        company=tenant_a.company, product=product, quantity=5, batch_no="LOT-MAIN", expiry_date=date(2030, 1, 1), warehouse=main,
        user=tenant_a.owner,
    )
    InventoryService.post_opening(
        company=tenant_a.company, product=product, quantity=5, batch_no="LOT-NORTH", expiry_date=date(2030, 1, 1), warehouse=north,
        user=tenant_a.owner,
    )
    resp = tenant_a.client.get("/api/v1/inventory/batches/", {"product": product.id, "warehouse": main.id})
    assert resp.status_code == 200, resp.data
    rows = resp.data["results"] if isinstance(resp.data, dict) and "results" in resp.data else resp.data
    assert [r["batch_no"] for r in rows] == ["LOT-MAIN"]
