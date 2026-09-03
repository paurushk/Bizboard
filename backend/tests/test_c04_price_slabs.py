"""C-04: qty slabs on party price lists; CN keeps original rate."""

from decimal import Decimal

import pytest

from masters.models import PriceList, PriceListItem
from masters.pricing import resolve_unit_price
from sales.models import SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _list_with_slabs(company, product):
    pl = PriceList.objects.create(company=company, name="Wholesale")
    PriceListItem.objects.create(
        company=company, price_list=pl, product=product,
        unit_price=Decimal("100"), min_qty=Decimal("1"), max_qty=Decimal("10"),
    )
    PriceListItem.objects.create(
        company=company, price_list=pl, product=product,
        unit_price=Decimal("92"), min_qty=Decimal("11"), max_qty=None,
    )
    return pl


def test_slab_qty_12_picks_11_plus(tenant_a):
    product = make_product(tenant_a.company, selling_price="120")
    pl = _list_with_slabs(tenant_a.company, product)
    customer = make_customer(tenant_a.company)
    customer.price_list = pl
    customer.save(update_fields=["price_list"])
    assert resolve_unit_price(customer=customer, product=product, quantity=12) == Decimal("92")
    assert resolve_unit_price(customer=customer, product=product, quantity=5) == Decimal("100")


def test_customer_without_list_uses_selling_price(tenant_a):
    product = make_product(tenant_a.company, selling_price="120")
    customer = make_customer(tenant_a.company)
    assert resolve_unit_price(customer=customer, product=product, quantity=12) == Decimal("120")


def test_invoice_line_snapshots_list_name(tenant_a):
    product = make_product(tenant_a.company, selling_price="120", gst_rate="0")
    add_stock(tenant_a, product, "100")
    pl = _list_with_slabs(tenant_a.company, product)
    customer = make_customer(tenant_a.company)
    customer.price_list = pl
    customer.save(update_fields=["price_list"])
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "12", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    line = invoice.items.get()
    assert line.unit_price == Decimal("92")
    assert line.applied_price_list_name == "Wholesale"


def test_cn_keeps_original_rate(tenant_a):
    product = make_product(tenant_a.company, selling_price="120", gst_rate="0")
    add_stock(tenant_a, product, "100")
    pl = _list_with_slabs(tenant_a.company, product)
    customer = make_customer(tenant_a.company)
    customer.price_list = pl
    customer.save(update_fields=["price_list"])
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "12", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    completed = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert completed.status_code == 200, completed.data
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    source = invoice.items.get()
    # Change today's list so a re-price would be obvious.
    PriceListItem.objects.filter(price_list=pl, min_qty=Decimal("11")).update(unit_price=Decimal("50"))
    cn = tenant_a.client.post(
        "/api/v1/sales/credit-notes/",
        {
            "customer": customer.id,
            "sales_invoice": invoice.id,
            "reason": "CORRECTION_OF_INVOICE",
            "items": [
                {
                    "product": product.id,
                    "quantity": "1",
                    "source_item": source.id,
                }
            ],
        },
        format="json",
    )
    assert cn.status_code in (200, 201), cn.data
    assert Decimal(str(cn.data["items"][0]["unit_price"])) == Decimal("92")


def test_overlapping_slabs_rejected(tenant_a):
    product = make_product(tenant_a.company, selling_price="120")
    resp = tenant_a.client.post(
        "/api/v1/masters/price-lists/",
        {
            "name": "Overlap",
            "items": [
                {
                    "product": product.id,
                    "unit_price": "100",
                    "min_qty": "1",
                    "max_qty": "20",
                },
                {
                    "product": product.id,
                    "unit_price": "90",
                    "min_qty": "10",
                    "max_qty": "30",
                },
            ],
        },
        format="json",
    )
    assert resp.status_code == 400, resp.data
    assert "overlap" in str(resp.data).lower()


def test_max_qty_below_min_qty_rejected(tenant_a):
    product = make_product(tenant_a.company, selling_price="120")
    resp = tenant_a.client.post(
        "/api/v1/masters/price-lists/",
        {
            "name": "Inverted",
            "items": [
                {
                    "product": product.id,
                    "unit_price": "100",
                    "min_qty": "10",
                    "max_qty": "5",
                },
            ],
        },
        format="json",
    )
    assert resp.status_code == 400, resp.data
    assert "max_qty" in str(resp.data).lower() or "min_qty" in str(resp.data).lower()
