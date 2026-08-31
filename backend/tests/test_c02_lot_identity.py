"""C-02: challan → invoice lot identity; opening unique; zero-cost SALE warns."""

from decimal import Decimal

import pytest
from django.db import IntegrityError

from inventory.models import MovementType, StockMovement
from inventory.services import InventoryService
from tests.conftest import add_stock, make_customer, make_product

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
