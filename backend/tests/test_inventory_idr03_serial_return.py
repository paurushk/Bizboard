"""INV-IDR-03 - a sold serial comes back through a sales return; the manual route is an owner's repair."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from accounts.models import CompanyUser, User
from core.models import AuditEvent
from inventory.models import MovementType, SerialNumber, StockMovement
from inventory.services import InventoryService
from tests.conftest import make_product

pytestmark = pytest.mark.django_db


def _sold_serial(tenant, sku="IDR3-1", number="IDR3-SN-1"):
    product = make_product(tenant.company, sku=sku, track_serial=True)
    warehouse = InventoryService.default_warehouse(tenant.company)
    return SerialNumber.objects.create(
        company=tenant.company, product=product, warehouse=warehouse, serial_number=number,
        status=SerialNumber.Status.SOLD,
    )


def _url(serial):
    return f"/api/v1/inventory/serials/{serial.pk}/transition/"


def _returns(tenant, serial):
    return StockMovement.objects.filter(
        company=tenant.company, movement_type=MovementType.SALES_RETURN,
        reference_type="serial_manual_return", reference_id=str(serial.pk),
    )


def _inventory_manager(tenant):
    user = User.objects.create_user(email="mgr-idr03@alpha.test", password="StrongPass123!")
    CompanyUser.objects.create(
        company=tenant.company, user=user, role=CompanyUser.Role.MANAGER, can_manage_inventory=True,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_only_an_owner_can_put_a_sold_unit_back_without_a_sales_return(tenant_a):
    serial = _sold_serial(tenant_a)
    manager = _inventory_manager(tenant_a)
    resp = manager.post(
        _url(serial), {"status": "AVAILABLE", "reason": "Customer brought it back", "confirm_no_document": True},
        format="json",
    )
    assert resp.status_code == 403, resp.data
    serial.refresh_from_db()
    assert serial.status == SerialNumber.Status.SOLD
    assert _returns(tenant_a, serial).count() == 0


def test_the_owner_must_give_a_reason_and_confirm(tenant_a):
    serial = _sold_serial(tenant_a, sku="IDR3-2", number="IDR3-SN-2")
    no_reason = tenant_a.client.post(_url(serial), {"status": "AVAILABLE", "confirm_no_document": True}, format="json")
    assert no_reason.status_code == 400, no_reason.data
    assert "sales_return_required" in str(no_reason.data)
    no_confirm = tenant_a.client.post(_url(serial), {"status": "AVAILABLE", "reason": "Came back"}, format="json")
    assert no_confirm.status_code == 400, no_confirm.data
    serial.refresh_from_db()
    assert serial.status == SerialNumber.Status.SOLD
    assert _returns(tenant_a, serial).count() == 0


def test_the_owners_manual_return_records_its_reason_in_the_movement_and_the_audit_log(tenant_a):
    serial = _sold_serial(tenant_a, sku="IDR3-3", number="IDR3-SN-3")
    resp = tenant_a.client.post(
        _url(serial),
        {"status": "AVAILABLE", "reason": "Credit note raised on paper", "confirm_no_document": True},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    serial.refresh_from_db()
    assert serial.status == SerialNumber.Status.AVAILABLE
    move = _returns(tenant_a, serial).get()
    assert "Credit note raised on paper" in move.reason
    assert AuditEvent.objects.filter(
        company=tenant_a.company, entity_type="SerialNumber", entity_id=str(serial.pk),
        description__contains="Credit note raised on paper",
    ).exists()


def test_a_repeated_request_with_the_same_key_returns_one_stock_movement(tenant_a):
    serial = _sold_serial(tenant_a, sku="IDR3-4", number="IDR3-SN-4")
    body = {"status": "AVAILABLE", "reason": "Came back", "confirm_no_document": True}
    first = tenant_a.client.post(_url(serial), body, format="json", HTTP_IDEMPOTENCY_KEY="idr3-k1")
    second = tenant_a.client.post(_url(serial), body, format="json", HTTP_IDEMPOTENCY_KEY="idr3-k1")
    assert first.status_code == second.status_code == 200
    assert _returns(tenant_a, serial).count() == 1


def test_a_second_request_after_the_unit_is_back_is_refused_not_posted_twice(tenant_a):
    serial = _sold_serial(tenant_a, sku="IDR3-5", number="IDR3-SN-5")
    body = {"status": "AVAILABLE", "reason": "Came back", "confirm_no_document": True}
    assert tenant_a.client.post(_url(serial), body, format="json", HTTP_IDEMPOTENCY_KEY="idr3-a").status_code == 200
    again = tenant_a.client.post(_url(serial), body, format="json", HTTP_IDEMPOTENCY_KEY="idr3-b")
    assert again.status_code == 400
    assert _returns(tenant_a, serial).count() == 1


def test_the_sale_document_lookup_lives_under_serials(tenant_a):
    """The Serial numbers page called /serial-numbers/ (a path that does not exist); the route is /serials/."""
    serial = _sold_serial(tenant_a, sku="IDR3-7", number="IDR3-SN-7")
    ok = tenant_a.client.get(f"/api/v1/inventory/serials/{serial.pk}/document/")
    assert ok.status_code == 200, ok.data
    assert tenant_a.client.get(f"/api/v1/inventory/serial-numbers/{serial.pk}/document/").status_code == 404


def test_the_unit_cannot_be_sent_to_the_in_transit_godown(tenant_a):
    from inventory.models import Warehouse

    serial = _sold_serial(tenant_a, sku="IDR3-6", number="IDR3-SN-6")
    transit = Warehouse.objects.create(company=tenant_a.company, name="In transit", code="TRANSIT", is_system=True)
    resp = tenant_a.client.post(
        _url(serial),
        {"status": "AVAILABLE", "reason": "x", "confirm_no_document": True, "warehouse": transit.pk},
        format="json",
    )
    assert resp.status_code == 400, resp.data
    assert _returns(tenant_a, serial).count() == 0
