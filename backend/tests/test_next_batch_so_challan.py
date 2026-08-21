"""Next batch: SO CONFIRMED reservation + stock_on_delivery_challan."""

from decimal import Decimal

import pytest

from inventory.models import MovementType, StockBalance, StockMovement
from sales.models import SalesOrder
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


def test_confirm_reserves_cancel_releases(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    order, _ = _draft_order(tenant_a, product, qty="4")

    confirmed = tenant_a.client.post(f"/api/v1/sales/orders/{order.id}/confirm/")
    assert confirmed.status_code == 200, confirmed.data
    assert confirmed.data["status"] == "CONFIRMED"

    balance = StockBalance.objects.get(company=tenant_a.company, product=product)
    assert balance.reserved == Decimal("4")
    assert balance.available == Decimal("6")

    cancelled = tenant_a.client.post(f"/api/v1/sales/orders/{order.id}/cancel/")
    assert cancelled.status_code == 200, cancelled.data
    assert cancelled.data["status"] == "CANCELLED"

    balance.refresh_from_db()
    assert balance.reserved == Decimal("0")
    assert balance.available == Decimal("10")


def test_confirm_insufficient_available_under_block_fails(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "2")
    tenant_a.company.negative_stock_policy = "BLOCK"
    tenant_a.company.save(update_fields=["negative_stock_policy"])
    order, _ = _draft_order(tenant_a, product, qty="5")

    resp = tenant_a.client.post(f"/api/v1/sales/orders/{order.id}/confirm/")
    assert resp.status_code == 400
    order.refresh_from_db()
    assert order.status == "DRAFT"
    balance = StockBalance.objects.get(company=tenant_a.company, product=product)
    assert balance.reserved == Decimal("0")


def test_challan_with_flag_posts_stock_once(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    tenant_a.company.stock_on_delivery_challan = True
    tenant_a.company.save(update_fields=["stock_on_delivery_challan"])
    customer = make_customer(tenant_a.company)

    challan_resp = tenant_a.client.post(
        "/api/v1/sales/delivery-challans/",
        {
            "customer": customer.id,
            "items": [
                {
                    "product": product.id,
                    "quantity": "3",
                    "unit_price": "100",
                    "gst_rate": "0",
                }
            ],
        },
        format="json",
    )
    assert challan_resp.status_code == 201, challan_resp.data
    done = tenant_a.client.post(
        f"/api/v1/sales/delivery-challans/{challan_resp.data['id']}/complete/"
    )
    assert done.status_code == 200, done.data
    assert done.data["stock_posted"] is True

    sales = StockMovement.objects.filter(
        company=tenant_a.company,
        product=product,
        movement_type=MovementType.SALE,
        reference_type="delivery_challan",
        reference_id=str(challan_resp.data["id"]),
    )
    assert sales.count() == 1
    balance = StockBalance.objects.get(company=tenant_a.company, product=product)
    assert balance.on_hand == Decimal("7")

    # Convert + complete invoice must not post a second SALE for the same qty.
    inv_resp = tenant_a.client.post(
        f"/api/v1/sales/delivery-challans/{challan_resp.data['id']}/convert/"
    )
    assert inv_resp.status_code == 200, inv_resp.data
    complete = tenant_a.client.post(f"/api/v1/sales/invoices/{inv_resp.data['id']}/complete/")
    assert complete.status_code == 200, complete.data

    assert (
        StockMovement.objects.filter(
            company=tenant_a.company, product=product, movement_type=MovementType.SALE
        ).count()
        == 1
    )
    balance.refresh_from_db()
    assert balance.on_hand == Decimal("7")


def test_convert_confirmed_order_releases_reservation(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    order, _ = _draft_order(tenant_a, product, qty="2")
    SalesNotesService.confirm_sales_order(order, tenant_a.owner)
    balance = StockBalance.objects.get(company=tenant_a.company, product=product)
    assert balance.reserved == Decimal("2")

    invoice = SalesNotesService.convert_sales_order(order, tenant_a.owner)
    balance.refresh_from_db()
    assert balance.reserved == Decimal("0")
    order.refresh_from_db()
    assert order.status == SalesOrder.Status.CONVERTED
    assert order.converted_invoice_id == invoice.id
