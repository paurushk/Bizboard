"""A6 — Manual serial SOLD→RETURNED (CR-048, CR-049) + scrap guard (CR-057)."""

from decimal import Decimal

import pytest
from django.db.models import Sum

from inventory.models import InventoryCostLayer, MovementType, SerialNumber, StockBalance, StockMovement
from inventory.services import InventoryService
from tests.conftest import create_draft_invoice, make_customer, make_product


@pytest.fixture
def fifo_company(tenant_a):
    company = tenant_a.company
    company.inventory_valuation_method = "FIFO"
    company.save(update_fields=["inventory_valuation_method"])
    return tenant_a


def test_serial_transition_sold_to_returned_succeeds(fifo_company):
    """CR-048: no FieldError; CR-049: AVAILABLE + peels restore + re-sellable."""
    tenant = fifo_company
    product = make_product(tenant.company, sku="A6-SN-1", track_serial=True, purchase_price="40")
    customer = make_customer(tenant.company)
    wh = InventoryService.default_warehouse(tenant.company)
    InventoryService.post_movement(
        company=tenant.company,
        warehouse=wh,
        product=product,
        movement_type=MovementType.PURCHASE,
        quantity="1",
        unit_cost="40",
        user=tenant.owner,
    )
    SerialNumber.objects.create(
        company=tenant.company,
        product=product,
        warehouse=wh,
        serial_number="A6-SN-RET",
    )
    inv = create_draft_invoice(
        tenant,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "serial_numbers": ["A6-SN-RET"]}],
    )
    assert tenant.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200

    serial = SerialNumber.objects.get(company=tenant.company, serial_number="A6-SN-RET")
    assert serial.status == SerialNumber.Status.SOLD
    assert StockBalance.objects.get(product=product, warehouse=wh, batch__isnull=True).on_hand == Decimal("0")

    ret = tenant.client.post(
        f"/api/v1/inventory/serials/{serial.id}/transition/",
        {"status": SerialNumber.Status.RETURNED},
        format="json",
    )
    assert ret.status_code == 200, ret.data
    assert ret.data["status"] == SerialNumber.Status.AVAILABLE
    serial.refresh_from_db()
    assert serial.status == SerialNumber.Status.AVAILABLE

    assert StockMovement.objects.filter(
        company=tenant.company,
        product=product,
        movement_type=MovementType.SALES_RETURN,
        reference_type="serial_manual_return",
        reference_id=str(serial.pk),
    ).exists()
    balance = StockBalance.objects.get(product=product, warehouse=wh, batch__isnull=True)
    assert balance.on_hand == Decimal("1")
    layer_sum = (
        InventoryCostLayer.objects.filter(
            company=tenant.company, product=product, warehouse=wh, qty_remaining__gt=0
        ).aggregate(total=Sum("qty_remaining"))["total"]
        or Decimal("0")
    )
    assert layer_sum == balance.on_hand

    inv2 = create_draft_invoice(
        tenant,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "110", "serial_numbers": ["A6-SN-RET"]}],
    )
    done = tenant.client.post(f"/api/v1/sales/invoices/{inv2['id']}/complete/")
    assert done.status_code == 200, done.data
    serial.refresh_from_db()
    assert serial.status == SerialNumber.Status.SOLD


@pytest.mark.no_invariant_check  # deliberately builds inconsistent state to test detection/rejection
def test_serial_scrap_available_requires_on_hand(tenant_a):
    """CR-057: AVAILABLE scrap refuses when on_hand < 1."""
    product = make_product(tenant_a.company, sku="A6-SCRAP", track_serial=True)
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    serial = SerialNumber.objects.create(
        company=tenant_a.company,
        product=product,
        warehouse=warehouse,
        serial_number="A6-SCRAP-1",
        status=SerialNumber.Status.AVAILABLE,
    )
    # No stock posted — on_hand is 0 / missing.
    resp = tenant_a.client.post(
        f"/api/v1/inventory/serials/{serial.id}/transition/",
        {"status": SerialNumber.Status.SCRAPPED},
        format="json",
    )
    assert resp.status_code == 400, resp.data
    serial.refresh_from_db()
    assert serial.status == SerialNumber.Status.AVAILABLE
