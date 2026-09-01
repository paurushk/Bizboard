"""Sprint 3: FIFO cancel, serial SM, opening/serial uniqueness, SO warehouse."""

from decimal import Decimal

import pytest
from django.db import IntegrityError

from inventory.models import BatchLot, InventoryCostLayer, MovementType, SerialNumber, Warehouse
from inventory.services import InventoryService, StockTransferService
from inventory.models import StockTransfer, StockTransferLine
from sales.models import SalesInvoice, SalesOrder
from tests.conftest import create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def test_bb_000601_fifo_cancel_recreates_layers_and_resell(tenant_a):
    company = tenant_a.company
    company.inventory_valuation_method = "FIFO"
    company.save(update_fields=["inventory_valuation_method"])
    product = make_product(company, sku="FIFO-1")
    wh = InventoryService.default_warehouse(company)
    InventoryService.post_movement(
        company=company, product=product, warehouse=wh,
        movement_type=MovementType.PURCHASE, quantity="1", unit_cost="10", user=tenant_a.owner,
    )
    InventoryService.post_movement(
        company=company, product=product, warehouse=wh,
        movement_type=MovementType.PURCHASE, quantity="1", unit_cost="20", user=tenant_a.owner,
    )
    customer = make_customer(company)
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    remaining = list(InventoryCostLayer.objects.filter(company=company, product=product, qty_remaining__gt=0))
    assert sum((l.qty_remaining for l in remaining), Decimal("0")) == Decimal("1")
    assert remaining[0].unit_cost == Decimal("20")

    cancel = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/cancel/")
    assert cancel.status_code == 200, cancel.data
    layers = list(InventoryCostLayer.objects.filter(company=company, product=product, qty_remaining__gt=0).order_by("id"))
    assert sum((l.qty_remaining for l in layers), Decimal("0")) == Decimal("2")

    inv2 = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv2['id']}/complete/")
    assert done.status_code == 200, done.data


def test_bb_000601_transfer_preserves_out_cost(tenant_a):
    company = tenant_a.company
    company.inventory_valuation_method = "FIFO"
    company.save(update_fields=["inventory_valuation_method"])
    product = make_product(company, sku="TRF-C")
    source = InventoryService.default_warehouse(company)
    dest = Warehouse.objects.create(company=company, name="Branch", code="BR2")
    InventoryService.post_movement(
        company=company, product=product, warehouse=source,
        movement_type=MovementType.PURCHASE, quantity="2", unit_cost="15", user=tenant_a.owner,
    )
    transfer = StockTransfer.objects.create(company=company, from_warehouse=source, to_warehouse=dest)
    StockTransferLine.objects.create(transfer=transfer, product=product, quantity="2")
    StockTransferService.complete(transfer, tenant_a.owner)
    in_layer = InventoryCostLayer.objects.filter(
        company=company, product=product, warehouse=dest, qty_remaining__gt=0
    ).first()
    assert in_layer is not None
    assert in_layer.unit_cost == Decimal("15")


def test_bb_000615_sale_return_makes_serial_available(tenant_a):
    product = make_product(tenant_a.company, sku="SER-1", track_serial=True)
    customer = make_customer(tenant_a.company)
    wh = InventoryService.default_warehouse(tenant_a.company)
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=wh, product=product,
        movement_type=MovementType.PURCHASE, quantity="1", unit_cost="10",
    )
    SerialNumber.objects.create(
        company=tenant_a.company, product=product, warehouse=wh, serial_number="SN-RET",
    )
    inv = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "serial_numbers": ["SN-RET"]}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    ret = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {"sales_invoice": inv["id"], "customer": customer.id, "items": [
            {"product": product.id, "quantity": "1", "unit_price": "100", "serial_numbers": ["SN-RET"]},
        ]},
        format="json",
    )
    assert ret.status_code == 201, ret.data
    rid = ret.data["id"]
    done = tenant_a.client.post(f"/api/v1/sales/returns/{rid}/complete/")
    assert done.status_code == 200, done.data
    serial = SerialNumber.objects.get(company=tenant_a.company, product=product, serial_number="SN-RET")
    assert serial.status == SerialNumber.Status.AVAILABLE

    inv2 = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "serial_numbers": ["SN-RET"]}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv2['id']}/complete/").status_code == 200


def test_bb_000615_cancel_return_restores_sold_serial(tenant_a):
    product = make_product(tenant_a.company, sku="SER-2", track_serial=True)
    customer = make_customer(tenant_a.company)
    wh = InventoryService.default_warehouse(tenant_a.company)
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=wh, product=product,
        movement_type=MovementType.PURCHASE, quantity="1", unit_cost="10",
    )
    SerialNumber.objects.create(
        company=tenant_a.company, product=product, warehouse=wh, serial_number="SN-CXL",
    )
    inv = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "serial_numbers": ["SN-CXL"]}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    ret = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {"sales_invoice": inv["id"], "customer": customer.id, "items": [
            {"product": product.id, "quantity": "1", "unit_price": "100", "serial_numbers": ["SN-CXL"]},
        ]},
        format="json",
    )
    rid = ret.data["id"]
    assert tenant_a.client.post(f"/api/v1/sales/returns/{rid}/complete/").status_code == 200
    assert tenant_a.client.post(f"/api/v1/sales/returns/{rid}/cancel/").status_code == 200
    serial = SerialNumber.objects.get(company=tenant_a.company, serial_number="SN-CXL")
    assert serial.status == SerialNumber.Status.SOLD


def test_bb_000660_opening_stock_unique_per_batch(tenant_a):
    product = make_product(tenant_a.company, sku="LOT-1", track_batch=True)
    wh = InventoryService.default_warehouse(tenant_a.company)
    lot_a = BatchLot.objects.create(company=tenant_a.company, product=product, batch_no="A")
    lot_b = BatchLot.objects.create(company=tenant_a.company, product=product, batch_no="B")
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=wh, product=product, batch=lot_a,
        movement_type=MovementType.OPENING_STOCK, quantity="5", unit_cost="10",
    )
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=wh, product=product, batch=lot_b,
        movement_type=MovementType.OPENING_STOCK, quantity="3", unit_cost="12",
    )
    with pytest.raises(Exception):
        InventoryService.post_movement(
            company=tenant_a.company, warehouse=wh, product=product, batch=lot_a,
            movement_type=MovementType.OPENING_STOCK, quantity="1", unit_cost="10",
        )


def test_bb_000667_serial_unique_per_company_product(tenant_a):
    p1 = make_product(tenant_a.company, sku="P1")
    p2 = make_product(tenant_a.company, sku="P2")
    SerialNumber.objects.create(company=tenant_a.company, product=p1, serial_number="SN001")
    SerialNumber.objects.create(company=tenant_a.company, product=p2, serial_number="SN001")
    with pytest.raises(IntegrityError):
        SerialNumber.objects.create(company=tenant_a.company, product=p1, serial_number="SN001")


def test_bb_000659_so_reserves_and_converts_same_warehouse(tenant_a):
    product = make_product(tenant_a.company, sku="WH-1")
    customer = make_customer(tenant_a.company)
    default = InventoryService.default_warehouse(tenant_a.company)
    branch = Warehouse.objects.create(company=tenant_a.company, name="East", code="EAST")
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=branch, product=product,
        movement_type=MovementType.PURCHASE, quantity="5", unit_cost="10",
    )
    created = tenant_a.client.post(
        "/api/v1/sales/orders/",
        {
            "customer": customer.id,
            "warehouse": branch.id,
            "items": [{"product": product.id, "quantity": "2", "unit_price": "100"}],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    oid = created.data["id"]
    confirmed = tenant_a.client.post(f"/api/v1/sales/orders/{oid}/confirm/")
    assert confirmed.status_code == 200, confirmed.data
    order = SalesOrder.objects.get(pk=oid)
    assert order.warehouse_id == branch.id
    from inventory.models import StockBalance

    bal = StockBalance.objects.get(company=tenant_a.company, warehouse=branch, product=product, batch=None)
    assert bal.reserved == Decimal("2")
    converted = tenant_a.client.post(f"/api/v1/sales/orders/{oid}/convert/")
    assert converted.status_code == 200, converted.data
    inv_id = converted.data["id"]
    invoice = SalesInvoice.objects.get(pk=inv_id)
    assert invoice.warehouse_id == branch.id
    assert invoice.warehouse_id != default.id
