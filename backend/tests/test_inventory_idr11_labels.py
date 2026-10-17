"""INV-IDR-11 - the thermal-printer label carries what the shelf label carries."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from inventory.models import BatchLot
from masters.models import Product
from tests.conftest import make_product

pytestmark = pytest.mark.django_db

ZPL = "/api/v1/inventory/labels.zpl"


def _product(tenant, sku="LB-1", name="Green Tea", **extra):
    product = make_product(tenant.company, sku=sku, name=name)
    Product.objects.filter(pk=product.pk).update(
        barcode=extra.pop("barcode", "8901234567890"),
        mrp=extra.pop("mrp", Decimal("120")),
        selling_price=extra.pop("selling_price", Decimal("100")),
        **extra,
    )
    return Product.objects.get(pk=product.pk)


def _text(response):
    return response.content.decode()


def test_label_has_name_barcode_price_and_the_label_size(tenant_a):
    product = _product(tenant_a)
    body = _text(tenant_a.client.get(ZPL, {"product": product.id, "size": "medium"}))
    assert "^PW650" in body and "^LL406" in body
    assert "^FDGreen Tea^FS" in body
    assert "^FD8901234567890^FS" in body
    assert "Rs 120.00" in body  # the MRP, as on the shelf label


def test_price_falls_back_to_the_selling_price_when_there_is_no_mrp(tenant_a):
    product = _product(tenant_a, mrp=Decimal("0"), selling_price=Decimal("99.5"))
    assert "Rs 99.50" in _text(tenant_a.client.get(ZPL, {"product": product.id}))


def test_price_can_be_left_off(tenant_a):
    product = _product(tenant_a)
    assert "Rs " not in _text(tenant_a.client.get(ZPL, {"product": product.id, "price": "0"}))


def test_a_lot_adds_its_batch_and_expiry(tenant_a):
    product = _product(tenant_a)
    lot = BatchLot.objects.create(
        company=tenant_a.company, product=product, batch_no="B-77", expiry_date=date(2027, 3, 31),
    )
    body = _text(tenant_a.client.get(ZPL, {"product": product.id, "batch": lot.id}))
    assert "Batch B-77  Exp 2027-03-31" in body


def test_a_lot_of_another_item_is_not_accepted(tenant_a):
    product = _product(tenant_a)
    other = _product(tenant_a, sku="LB-2", name="Other", barcode="123")
    lot = BatchLot.objects.create(company=tenant_a.company, product=other, batch_no="X-1")
    assert tenant_a.client.get(ZPL, {"product": product.id, "batch": lot.id}).status_code == 404


def test_copies_repeat_the_label_and_are_capped(tenant_a):
    product = _product(tenant_a)
    assert _text(tenant_a.client.get(ZPL, {"product": product.id, "copies": 3})).count("^XA") == 3
    assert _text(tenant_a.client.get(ZPL, {"product": product.id, "copies": 500})).count("^XA") == 50


def test_a_code_that_cannot_be_a_barcode_is_refused_by_name(tenant_a):
    product = _product(tenant_a, barcode="चाय-1")
    resp = tenant_a.client.get(ZPL, {"product": product.id})
    assert resp.status_code == 400
    assert "Green Tea" in str(resp.data)


def test_one_file_for_several_items(tenant_a):
    first = _product(tenant_a)
    second = _product(tenant_a, sku="LB-2", name="Palm Oil", barcode="8909999999999")
    resp = tenant_a.client.post(
        ZPL, {"labels": [{"product": first.id, "copies": 2}, {"product": second.id, "copies": 1}], "size": "large"},
        format="json",
    )
    assert resp.status_code == 200
    body = _text(resp)
    assert body.count("^XA") == 3 and "^PW812" in body
    assert "Green Tea" in body and "Palm Oil" in body


def test_a_run_over_the_limit_is_refused(tenant_a):
    product = _product(tenant_a)
    rows = [{"product": product.id, "copies": 50}] * 11
    assert tenant_a.client.post(ZPL, {"labels": rows}, format="json").status_code == 400


def test_a_post_without_labels_is_refused(tenant_a):
    assert tenant_a.client.post(ZPL, {"labels": []}, format="json").status_code == 400


def test_items_without_a_barcode_are_counted_and_paged(tenant_a):
    for i in range(3):
        _product(tenant_a, sku=f"NB-{i}", name=f"Plain {i}", barcode="")
    _product(tenant_a, sku="HB-1", name="Has one")
    inactive = _product(tenant_a, sku="NB-X", name="Dormant", barcode="")
    Product.objects.filter(pk=inactive.pk).update(status=Product.Status.INACTIVE)
    resp = tenant_a.client.get("/api/v1/products/missing-barcode/", {"page_size": 2})
    assert resp.status_code == 200
    assert resp.data["count"] == 3
    assert len(resp.data["results"]) == 2
