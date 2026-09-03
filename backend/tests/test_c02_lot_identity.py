"""C-02: challan → invoice lot identity; opening unique; zero-cost SALE warns."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError

from inventory.models import BatchLot, MovementType, SerialNumber, StockMovement
from inventory.services import InventoryService
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db


def _complete_challan_with_serial(tenant, serial="SN-A"):
    product = make_product(tenant.company, sku="C02-SN", track_serial=True)
    InventoryService.post_opening(
        company=tenant.company,
        product=product,
        quantity="1",
        serial_numbers=[serial],
        user=tenant.owner,
    )
    customer = make_customer(tenant.company)
    create = tenant.client.post(
        "/api/v1/sales/delivery-challans/",
        {
            "customer": customer.id,
            "items": [
                {
                    "product": product.id,
                    "quantity": "1",
                    "unit_price": "100",
                    "gst_rate": "0",
                    "serial_numbers": [serial],
                }
            ],
        },
        format="json",
    )
    assert create.status_code == 201, create.data
    done = tenant.client.post(f"/api/v1/sales/delivery-challans/{create.data['id']}/complete/")
    assert done.status_code == 200, done.data
    converted = tenant.client.post(f"/api/v1/sales/delivery-challans/{create.data['id']}/convert/")
    assert converted.status_code == 200, converted.data
    return product, converted.data["id"]


def test_challan_serial_mismatch_on_invoice_complete_is_400(tenant_a):
    product, invoice_id = _complete_challan_with_serial(tenant_a, serial="SN-A")
    patched = tenant_a.client.patch(
        f"/api/v1/sales/invoices/{invoice_id}/",
        {
            "items": [
                {
                    "product": product.id,
                    "quantity": "1",
                    "unit_price": "100",
                    "gst_rate": "0",
                    "serial_numbers": ["SN-B"],
                }
            ],
        },
        format="json",
    )
    assert patched.status_code == 200, patched.data
    blocked = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice_id}/complete/")
    assert blocked.status_code == 400
    body = blocked.data.get("error") or blocked.data
    assert "serial" in str(body).lower() or "challan" in str(body).lower()


def test_challan_matching_serial_completes(tenant_a):
    _product, invoice_id = _complete_challan_with_serial(tenant_a, serial="SN-A")
    ok = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice_id}/complete/")
    assert ok.status_code == 200, ok.data


def test_opening_twice_same_sku_warehouse_batch_integrity(tenant_a):
    product = make_product(tenant_a.company, sku="C02-OPEN")
    add_stock(tenant_a, product, "5")
    with pytest.raises(IntegrityError):
        StockMovement.objects.create(
            company=tenant_a.company,
            warehouse=InventoryService.default_warehouse(tenant_a.company),
            product=product,
            movement_type=MovementType.OPENING_STOCK,
            quantity=Decimal("1"),
            unit_cost=Decimal("10"),
        )


def test_zero_cost_sale_warns_on_complete(tenant_a):
    product = make_product(tenant_a.company, sku="C02-Z", purchase_price="0")
    add_stock(tenant_a, product, "1", unit_cost="0")
    customer = make_customer(tenant_a.company)
    draft = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": customer.id,
            "invoice_type": "NON_GST",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "50", "gst_rate": "0"}],
        },
        format="json",
    )
    assert draft.status_code == 201, draft.data
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{draft.data['id']}/complete/")
    assert done.status_code == 200, done.data
    warnings = done.data.get("warnings") or []
    assert any("COGS" in str(w) or "cost basis" in str(w) for w in warnings)


def test_fefo_persists_all_allocated_batch_nos(tenant_a):
    product = make_product(tenant_a.company, sku="C02-FEFO", track_batch=True)
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    early = BatchLot.objects.create(
        company=tenant_a.company,
        product=product,
        batch_no="LOT-A",
        expiry_date=date.today() + timedelta(days=5),
    )
    late = BatchLot.objects.create(
        company=tenant_a.company,
        product=product,
        batch_no="LOT-B",
        expiry_date=date.today() + timedelta(days=25),
    )
    for lot, qty in ((early, "10"), (late, "20")):
        InventoryService.post_movement(
            company=tenant_a.company,
            warehouse=warehouse,
            product=product,
            batch=lot,
            movement_type=MovementType.PURCHASE,
            quantity=qty,
            unit_cost="10",
            user=tenant_a.owner,
        )
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "25", "unit_price": "40"}],
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data
    from sales.models import SalesInvoice

    line = SalesInvoice.objects.get(pk=inv["id"]).items.get()
    nos = {n.strip() for n in (line.batch_no or "").split(",") if n.strip()}
    assert nos == {"LOT-A", "LOT-B"}


def test_purchase_complete_rejects_expiry_mismatch(tenant_a):
    product = make_product(tenant_a.company, sku="C02-EXP", track_batch=True)
    BatchLot.objects.create(
        company=tenant_a.company,
        product=product,
        batch_no="LOT1",
        expiry_date=date.today() + timedelta(days=30),
    )
    supplier = make_supplier(tenant_a.company)
    draft = create_draft_purchase(
        tenant_a,
        supplier,
        [
            {
                "product": product.id,
                "quantity": "1",
                "unit_price": "10",
                "batch_no": "LOT1",
                "exp_date": (date.today() + timedelta(days=90)).isoformat(),
            }
        ],
    )
    done = tenant_a.client.post(f"/api/v1/purchases/invoices/{draft['id']}/complete/")
    assert done.status_code == 400, done.data
    assert "expiry" in str(done.data).lower()


def test_manual_serial_blocks_stock_desync_transitions(tenant_a):
    product = make_product(tenant_a.company, sku="C02-SN-T", track_serial=True)
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    serial = SerialNumber.objects.create(
        company=tenant_a.company,
        product=product,
        warehouse=warehouse,
        serial_number="SN-DESYNC",
        status=SerialNumber.Status.AVAILABLE,
    )
    sold = tenant_a.client.post(
        f"/api/v1/inventory/serials/{serial.id}/transition/",
        {"status": SerialNumber.Status.SOLD},
        format="json",
    )
    assert sold.status_code == 400, sold.data
    serial.status = SerialNumber.Status.RETURNED
    serial.save(update_fields=["status"])
    available = tenant_a.client.post(
        f"/api/v1/inventory/serials/{serial.id}/transition/",
        {"status": SerialNumber.Status.AVAILABLE},
        format="json",
    )
    assert available.status_code == 400, available.data
    scrap = tenant_a.client.post(
        f"/api/v1/inventory/serials/{serial.id}/transition/",
        {"status": SerialNumber.Status.SCRAPPED},
        format="json",
    )
    assert scrap.status_code == 200, scrap.data


def test_sales_return_cancel_refuses_missing_movements(tenant_a):
    product = make_product(tenant_a.company, sku="C02-SR-MISS")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "50"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    ret = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {
            "customer": customer.id,
            "sales_invoice": inv["id"],
            "items": [{"product": product.id, "quantity": "1", "unit_price": "50"}],
        },
        format="json",
    )
    assert ret.status_code == 201, ret.data
    assert tenant_a.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/").status_code == 200
    StockMovement.objects.filter(
        reference_type__in=("sales_return", "sales_return_damaged"),
        reference_id=str(ret.data["id"]),
    ).delete()
    cancelled = tenant_a.client.post(f"/api/v1/sales/returns/{ret.data['id']}/cancel/")
    assert cancelled.status_code == 400, cancelled.data
    assert "missing" in str(cancelled.data).lower()
