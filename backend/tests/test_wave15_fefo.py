"""BB-000512: FEFO / SO reservation / delivery challan cancel-convert matrix."""

from decimal import Decimal

import pytest

from inventory.models import MovementType, StockBalance, StockMovement
from sales.models import DeliveryChallan, SalesOrder
from sales.notes_services import SalesNotesService
from tests.conftest import add_stock, make_customer, make_product

pytestmark = pytest.mark.django_db


def _draft_order(tenant, product, qty="3"):
    customer = make_customer(tenant.company)
    resp = tenant.client.post(
        "/api/v1/sales/orders/",
        {
            "customer": customer.id,
            "invoice_type": "NON_GST",
            "items": [
                {
                    "product": product.id,
                    "quantity": qty,
                    "unit_price": "100",
                    "gst_rate": "0",
                }
            ],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    return SalesOrder.objects.get(pk=resp.data["id"]), customer


def test_confirmed_order_cancel_releases_fefo_reservation(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    order, _ = _draft_order(tenant_a, product, qty="5")

    confirm = tenant_a.client.post(f"/api/v1/sales/orders/{order.id}/confirm/")
    assert confirm.status_code == 200
    balance = StockBalance.objects.get(company=tenant_a.company, product=product)
    assert balance.reserved == Decimal("5")

    cancel = tenant_a.client.post(f"/api/v1/sales/orders/{order.id}/cancel/")
    assert cancel.status_code == 200
    balance.refresh_from_db()
    assert balance.reserved == Decimal("0")
    assert balance.available == Decimal("10")


def test_convert_confirmed_order_clears_reservation_before_invoice(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "8")
    order, _ = _draft_order(tenant_a, product, qty="3")
    SalesNotesService.confirm_sales_order(order, tenant_a.owner)

    balance = StockBalance.objects.get(company=tenant_a.company, product=product)
    assert balance.reserved == Decimal("3")

    invoice = SalesNotesService.convert_sales_order(order, tenant_a.owner)
    balance.refresh_from_db()
    assert balance.reserved == Decimal("0")
    order.refresh_from_db()
    assert order.status == SalesOrder.Status.CONVERTED
    assert order.converted_invoice_id == invoice.id


def test_completed_challan_cancel_restores_stock(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    tenant_a.company.stock_on_delivery_challan = True
    tenant_a.company.save(update_fields=["stock_on_delivery_challan"])
    customer = make_customer(tenant_a.company)

    create = tenant_a.client.post(
        "/api/v1/sales/delivery-challans/",
        {
            "customer": customer.id,
            "items": [
                {
                    "product": product.id,
                    "quantity": "4",
                    "unit_price": "100",
                    "gst_rate": "0",
                }
            ],
        },
        format="json",
    )
    assert create.status_code == 201
    challan_id = create.data["id"]

    complete = tenant_a.client.post(f"/api/v1/sales/delivery-challans/{challan_id}/complete/")
    assert complete.status_code == 200
    balance = StockBalance.objects.get(company=tenant_a.company, product=product)
    assert balance.on_hand == Decimal("6")

    cancel = tenant_a.client.post(f"/api/v1/sales/delivery-challans/{challan_id}/cancel/")
    assert cancel.status_code == 200
    balance.refresh_from_db()
    assert balance.on_hand == Decimal("10")
    assert (
        StockMovement.objects.filter(
            company=tenant_a.company,
            product=product,
            movement_type=MovementType.ADJUSTMENT,
            reference_type="delivery_challan_cancel",
            reference_id=str(challan_id),
        ).exists()
    )
    challan = DeliveryChallan.objects.get(pk=challan_id)
    assert challan.status == DeliveryChallan.Status.CANCELLED
