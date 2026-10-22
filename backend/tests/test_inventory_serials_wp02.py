"""INV-WP-02 — the Serial numbers page only offers transitions the API accepts (review #2)."""

from __future__ import annotations

import pytest

from inventory.models import SerialNumber, StockBalance
from inventory.services import InventoryService
from tests.conftest import make_product

pytestmark = pytest.mark.django_db

LIST = "/api/v1/inventory/serials/"


def _transition(client, serial, target):
    return client.post(f"{LIST}{serial.id}/transition/", {"status": target}, format="json")


def _serial_product(tenant, sku):
    return make_product(tenant.company, sku=sku, track_serial=True)


@pytest.mark.invariant_skip("inventory.serial_traceability", reason="serial rows are created directly through the ORM, without a godown or movement")
def test_available_serial_cannot_be_marked_sold_by_hand(tenant_a):
    product = _serial_product(tenant_a, "SER-SOLD")
    serial = SerialNumber.objects.create(company=tenant_a.company, product=product, serial_number="A1")
    resp = _transition(tenant_a.client, serial, "SOLD")
    assert resp.status_code == 400
    serial.refresh_from_db()
    assert serial.status == SerialNumber.Status.AVAILABLE


def test_available_serial_can_be_scrapped_and_stock_drops(tenant_a):
    product = _serial_product(tenant_a, "SER-SCRAP")
    InventoryService.post_opening(
        company=tenant_a.company, product=product, quantity=2, serial_numbers=["S1", "S2"], user=tenant_a.owner,
    )
    serial = SerialNumber.objects.get(company=tenant_a.company, product=product, serial_number="S1")
    resp = _transition(tenant_a.client, serial, "SCRAPPED")
    assert resp.status_code == 200, resp.data
    serial.refresh_from_db()
    assert serial.status == SerialNumber.Status.SCRAPPED
    assert StockBalance.objects.get(company=tenant_a.company, product=product).on_hand == 1


def test_scrapped_serial_has_no_way_out(tenant_a):
    product = _serial_product(tenant_a, "SER-DEAD")
    serial = SerialNumber.objects.create(
        company=tenant_a.company, product=product, serial_number="D1", status=SerialNumber.Status.SCRAPPED,
    )
    for target in ("AVAILABLE", "SOLD", "RETURNED", "SCRAPPED"):
        assert _transition(tenant_a.client, serial, target).status_code == 400


@pytest.mark.invariant_skip("inventory.serial_traceability", reason="serial rows are created directly through the ORM, without a godown or movement")
def test_search_matches_part_of_a_serial_number(tenant_a):
    product = _serial_product(tenant_a, "SER-FIND")
    for number in ("ABC-100", "ABC-200", "XYZ-300"):
        SerialNumber.objects.create(company=tenant_a.company, product=product, serial_number=number)
    resp = tenant_a.client.get(LIST, {"q": "abc"})
    assert resp.status_code == 200
    rows = resp.data["results"] if isinstance(resp.data, dict) and "results" in resp.data else resp.data
    assert sorted(r["serial_number"] for r in rows) == ["ABC-100", "ABC-200"]


@pytest.mark.invariant_skip("inventory.serial_traceability", reason="serial rows are created directly through the ORM, without a godown or movement")
def test_document_link_is_empty_for_a_unit_that_is_not_sold_or_cannot_be_traced(tenant_a):
    product = _serial_product(tenant_a, "SER-DOC")
    available = SerialNumber.objects.create(company=tenant_a.company, product=product, serial_number="D1")
    resp = tenant_a.client.get(f"{LIST}{available.id}/document/")
    assert resp.status_code == 200 and resp.data == {"document": None}

    sold = SerialNumber.objects.create(
        company=tenant_a.company, product=product, serial_number="D2", status=SerialNumber.Status.SOLD,
    )
    resp = tenant_a.client.get(f"{LIST}{sold.id}/document/")
    assert resp.status_code == 200 and resp.data == {"document": None}


def test_document_link_points_at_the_invoice_a_unit_was_sold_on(tenant_a):
    from inventory.models import MovementType
    from tests.conftest import create_draft_invoice, make_customer

    product = make_product(tenant_a.company, sku="SER-LINK", track_serial=True, purchase_price="40")
    wh = InventoryService.default_warehouse(tenant_a.company)
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=wh, product=product, movement_type=MovementType.PURCHASE,
        quantity="1", unit_cost="40", user=tenant_a.owner,
    )
    serial = SerialNumber.objects.create(
        company=tenant_a.company, product=product, warehouse=wh, serial_number="LINK-1",
    )
    inv = create_draft_invoice(
        tenant_a, make_customer(tenant_a.company),
        [{"product": product.id, "quantity": "1", "unit_price": "100", "serial_numbers": ["LINK-1"]}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200

    resp = tenant_a.client.get(f"{LIST}{serial.id}/document/")
    assert resp.status_code == 200, resp.data
    doc = resp.data["document"]
    assert doc["type"] == "invoice" and doc["id"] == inv["id"]
    assert doc["path"] == f"/sales/invoices/{inv['id']}"
    assert doc["number"]
