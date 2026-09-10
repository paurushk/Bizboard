"""Edge cases for document completion that don't fit a single feature suite."""

from decimal import Decimal

import pytest

from inventory.models import MovementType, StockMovement
from masters.models import Product
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _make_service_product(tenant, name="Installation", sku="SVC-1"):
    resp = tenant.client.post(
        "/api/v1/products/",
        {
            "name": name,
            "sku": sku,
            "gst_rate": "18",
            "selling_price": "500",
            "product_type": Product.ProductType.SERVICE,
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    product = Product.objects.get(pk=resp.data["id"])
    # Product-type matrix must have cleared inventory tracking for a service.
    assert product.product_type == Product.ProductType.SERVICE
    assert product.track_inventory is False
    return product


def test_service_item_posts_no_stock_movement(tenant_a):
    """A SERVICE line completes without a stock pre-check or a stock movement.

    Previously this raised HTTP 400 `insufficient_stock` because the sales-invoice
    completion path ran InventoryService.check_negative_stock for every line,
    including non-inventory ones that have (and can have) no stock.
    """
    service = _make_service_product(tenant_a)
    customer = make_customer(tenant_a.company)
    invoice = create_draft_invoice(
        tenant_a, customer, [{"product": service.id, "quantity": "2", "unit_price": "500"}]
    )

    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice['id']}/complete/")

    assert resp.status_code == 200, resp.data
    assert not StockMovement.objects.filter(product=service).exists()


def test_service_line_alongside_goods_line_completes(tenant_a):
    """A mixed invoice: the goods line still deducts stock, the service line is skipped."""
    goods = make_product(tenant_a.company, name="Router", sku="RTR-1")
    add_stock(tenant_a, goods, "10")
    service = _make_service_product(tenant_a, name="Setup", sku="SVC-2")
    customer = make_customer(tenant_a.company)
    invoice = create_draft_invoice(
        tenant_a,
        customer,
        [
            {"product": goods.id, "quantity": "3", "unit_price": "100"},
            {"product": service.id, "quantity": "1", "unit_price": "500"},
        ],
    )

    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice['id']}/complete/")

    assert resp.status_code == 200, resp.data
    assert StockMovement.objects.filter(
        product=goods, movement_type=MovementType.SALE
    ).count() == 1
    assert not StockMovement.objects.filter(product=service).exists()
    from inventory.services import InventoryService

    assert InventoryService.available_quantity(tenant_a.company, goods) == Decimal("7")
