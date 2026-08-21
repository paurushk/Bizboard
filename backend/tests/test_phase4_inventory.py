from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.utils import timezone

from inventory.models import BatchLot, MovementType, SerialNumber, StockBalance, StockTransfer, StockTransferLine, Warehouse
from inventory.services import InventoryService, InventoryValuationService, StockTransferService
from tests.conftest import create_draft_invoice, make_customer, make_product


pytestmark = pytest.mark.django_db


def test_warehouse_backfill_is_available_for_legacy_callers(tenant_a):
    product = make_product(tenant_a.company)
    movement = InventoryService.post_movement(
        company=tenant_a.company, product=product, movement_type=MovementType.OPENING_STOCK, quantity="2"
    )
    assert movement.warehouse.is_default
    assert StockBalance.objects.get(company=tenant_a.company, product=product).warehouse == movement.warehouse


def test_transfer_conserves_stock_between_warehouses(tenant_a):
    product = make_product(tenant_a.company)
    source = InventoryService.default_warehouse(tenant_a.company)
    destination = Warehouse.objects.create(company=tenant_a.company, name="Store", code="STORE")
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=source, product=product,
        movement_type=MovementType.OPENING_STOCK, quantity="10",
    )
    transfer = StockTransfer.objects.create(
        company=tenant_a.company, from_warehouse=source, to_warehouse=destination
    )
    StockTransferLine.objects.create(transfer=transfer, product=product, quantity="4")
    StockTransferService.complete(transfer, tenant_a.owner)
    assert InventoryService.available_quantity(tenant_a.company, product, source) == Decimal("6")
    assert InventoryService.available_quantity(tenant_a.company, product, destination) == Decimal("4")
    StockTransferService.cancel(transfer, tenant_a.owner)
    assert InventoryService.available_quantity(tenant_a.company, product, source) == Decimal("10")
    assert InventoryService.available_quantity(tenant_a.company, product, destination) == Decimal("0")


def test_fefo_orders_earliest_expiry_first(tenant_a):
    product = make_product(tenant_a.company, track_batch=True)
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    later = BatchLot.objects.create(
        company=tenant_a.company, product=product, batch_no="LATE",
        expiry_date=timezone.localdate() + timedelta(days=20),
    )
    earlier = BatchLot.objects.create(
        company=tenant_a.company, product=product, batch_no="EARLY",
        expiry_date=timezone.localdate() + timedelta(days=5),
    )
    for batch in (later, earlier):
        InventoryService.post_movement(
            company=tenant_a.company, warehouse=warehouse, product=product, batch=batch,
            movement_type=MovementType.PURCHASE, quantity="1", unit_cost="10",
        )
    assert list(InventoryValuationService.fefo_batches(tenant_a.company, product, warehouse)) == [earlier, later]


def test_wavg_math(tenant_a):
    product = make_product(tenant_a.company)
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=warehouse, product=product,
        movement_type=MovementType.PURCHASE, quantity="10", unit_cost="10",
    )
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=warehouse, product=product,
        movement_type=MovementType.PURCHASE, quantity="10", unit_cost="20",
    )
    assert InventoryValuationService.unit_cost(tenant_a.company, product, warehouse) == Decimal("15")


def test_serial_is_unique_per_company(tenant_a):
    product = make_product(tenant_a.company)
    SerialNumber.objects.create(company=tenant_a.company, product=product, serial_number="SN-001")
    with pytest.raises(IntegrityError):
        SerialNumber.objects.create(company=tenant_a.company, product=product, serial_number="SN-001")


def test_sale_allocates_unselected_tracked_batch_by_fefo(tenant_a):
    product = make_product(tenant_a.company, track_batch=True)
    customer = make_customer(tenant_a.company)
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    early = BatchLot.objects.create(
        company=tenant_a.company, product=product, batch_no="EARLY",
        expiry_date=timezone.localdate() + timedelta(days=2),
    )
    late = BatchLot.objects.create(
        company=tenant_a.company, product=product, batch_no="LATE",
        expiry_date=timezone.localdate() + timedelta(days=10),
    )
    for lot in (early, late):
        InventoryService.post_movement(
            company=tenant_a.company, warehouse=warehouse, product=product, batch=lot,
            movement_type=MovementType.PURCHASE, quantity="1", unit_cost="10",
        )

    invoice = create_draft_invoice(tenant_a, customer, [{"product": product.id, "quantity": "1"}])
    response = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice['id']}/complete/")
    assert response.status_code == 200, response.data
    assert InventoryService.available_quantity(tenant_a.company, product, warehouse, early) == Decimal("0")
    assert InventoryService.available_quantity(tenant_a.company, product, warehouse, late) == Decimal("1")


def test_expired_batch_is_blocked_on_sale(tenant_a):
    tenant_a.company.block_expired_stock = True
    tenant_a.company.save(update_fields=["block_expired_stock"])
    product = make_product(tenant_a.company, track_batch=True)
    customer = make_customer(tenant_a.company)
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    expired = BatchLot.objects.create(
        company=tenant_a.company, product=product, batch_no="OLD",
        expiry_date=timezone.localdate() - timedelta(days=1),
    )
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=warehouse, product=product, batch=expired,
        movement_type=MovementType.PURCHASE, quantity="1", unit_cost="10",
    )
    invoice = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "batch": expired.id}]
    )
    response = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice['id']}/complete/")
    assert response.status_code == 400
    assert "expired" in str(response.data).lower()


def test_serial_sale_marks_available_serial_sold(tenant_a):
    product = make_product(tenant_a.company, track_serial=True)
    customer = make_customer(tenant_a.company)
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=warehouse, product=product,
        movement_type=MovementType.PURCHASE, quantity="1", unit_cost="10",
    )
    serial = SerialNumber.objects.create(
        company=tenant_a.company, product=product, warehouse=warehouse, serial_number="SN-SALE"
    )
    invoice = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "serial_numbers": ["SN-SALE"]}],
    )
    response = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice['id']}/complete/")
    assert response.status_code == 200, response.data
    serial.refresh_from_db()
    assert serial.status == SerialNumber.Status.SOLD


def test_serial_transfer_moves_warehouse_on_complete(tenant_a):
    product = make_product(tenant_a.company, track_serial=True)
    source = InventoryService.default_warehouse(tenant_a.company)
    destination = Warehouse.objects.create(company=tenant_a.company, name="Branch", code="BR")
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=source, product=product,
        movement_type=MovementType.OPENING_STOCK, quantity="1", unit_cost="10",
    )
    serial = SerialNumber.objects.create(
        company=tenant_a.company, product=product, warehouse=source, serial_number="SN-TRF",
    )
    transfer = StockTransfer.objects.create(
        company=tenant_a.company, from_warehouse=source, to_warehouse=destination,
    )
    StockTransferLine.objects.create(
        transfer=transfer, product=product, quantity="1", serial_numbers=["SN-TRF"],
    )
    StockTransferService.complete(transfer, tenant_a.owner)
    serial.refresh_from_db()
    assert serial.warehouse_id == destination.id
    assert serial.status == SerialNumber.Status.AVAILABLE


def _unwrap(resp_data):
    if isinstance(resp_data, dict) and "data" in resp_data and "success" in resp_data:
        return resp_data["data"]
    return resp_data


def test_price_list_item_available_via_api(tenant_a):
    product = make_product(tenant_a.company, selling_price="100")
    resp = tenant_a.client.post(
        "/api/v1/masters/price-lists/",
        {"name": "Retail", "items": [{"product": product.id, "unit_price": "85.00"}]},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    body = _unwrap(resp.data)
    list_id = body["id"]
    get_resp = tenant_a.client.get(f"/api/v1/masters/price-lists/{list_id}/")
    assert get_resp.status_code == 200
    listed = _unwrap(get_resp.data)
    items = listed.get("items") or []
    assert len(items) >= 1
    item = items[0]
    price = item.get("unit_price") or item.get("unitPrice")
    assert Decimal(str(price)) == Decimal("85.00")
    customer = make_customer(tenant_a.company)
    customer.price_list_id = list_id
    customer.save(update_fields=["price_list_id"])
    invoice = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "85.00"}],
    )
    inv = _unwrap(invoice) if isinstance(invoice, dict) and "data" in invoice else invoice
    line = inv["items"][0]
    assert Decimal(str(line.get("unit_price") or line.get("unitPrice"))) == Decimal("85")
