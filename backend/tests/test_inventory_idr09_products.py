"""INV-IDR-09 - the Items page filters on the server, and duplicate codes are a field error."""

from __future__ import annotations

from decimal import Decimal

import pytest

from masters.models import Brand, Category, Product
from tests.conftest import add_stock, make_product

pytestmark = pytest.mark.django_db

PRODUCTS = "/api/v1/products/"


def _rows(resp):
    assert resp.status_code == 200, resp.data
    data = resp.data
    return data["results"] if isinstance(data, dict) and "results" in data else data


def _names(resp):
    return {row["name"] for row in _rows(resp)}


@pytest.fixture
def catalogue(tenant_a):
    company = tenant_a.company
    tea_cat = Category.objects.create(company=company, name="Tea")
    oil_cat = Category.objects.create(company=company, name="Oil")
    acme = Brand.objects.create(company=company, name="Acme")
    tea = make_product(company, sku="P9-TEA", name="Green Tea", category=tea_cat, brand=acme, gst_rate=Decimal("5"))
    oil = make_product(company, sku="P9-OIL", name="Palm Oil", category=oil_cat, gst_rate=Decimal("12"))
    rice = make_product(company, sku="P9-RICE", name="Rice", gst_rate=Decimal("5"))
    add_stock(tenant_a, tea, "20")
    add_stock(tenant_a, oil, "2")
    # oil is at its reorder rule; rice has never been stocked
    Product.objects.filter(pk=oil.pk).update(reorder_level=Decimal("5"))
    return tenant_a, tea, oil, rice, tea_cat, oil_cat, acme


def test_category_brand_and_slab_filters_match_the_whole_catalogue(catalogue):
    tenant, _tea, _oil, _rice, tea_cat, oil_cat, acme = catalogue
    assert _names(tenant.client.get(PRODUCTS, {"category": tea_cat.id})) == {"Green Tea"}
    assert _names(tenant.client.get(PRODUCTS, {"category": oil_cat.id})) == {"Palm Oil"}
    assert _names(tenant.client.get(PRODUCTS, {"brand": acme.id})) == {"Green Tea"}
    assert _names(tenant.client.get(PRODUCTS, {"gst_rate": "5"})) == {"Green Tea", "Rice"}
    assert tenant.client.get(PRODUCTS, {"category": "abc"}).status_code == 400
    assert tenant.client.get(PRODUCTS, {"gst_rate": "abc"}).status_code == 400


def test_stock_status_in_includes_low_items_and_out_includes_never_stocked(catalogue):
    tenant, *_ = catalogue
    in_stock = _names(tenant.client.get(PRODUCTS, {"stock_status": "in"}))
    assert in_stock == {"Green Tea", "Palm Oil"}  # low items are still in stock
    assert _names(tenant.client.get(PRODUCTS, {"stock_status": "out"})) == {"Rice"}
    assert tenant.client.get(PRODUCTS, {"stock_status": "weird"}).status_code == 400


def test_stock_status_low_is_the_low_stock_pages_definition(catalogue):
    tenant, *_ = catalogue
    low = _names(tenant.client.get(PRODUCTS, {"stock_status": "low"}))
    assert "Palm Oil" in low and "Green Tea" not in low


def test_filters_combine(catalogue):
    tenant, _tea, _oil, _rice, tea_cat, *_ = catalogue
    assert _names(tenant.client.get(PRODUCTS, {"category": tea_cat.id, "stock_status": "out"})) == set()
    assert _names(tenant.client.get(PRODUCTS, {"gst_rate": "5", "stock_status": "out"})) == {"Rice"}


def test_filter_options_lists_what_is_in_use(catalogue):
    tenant, *_ = catalogue
    data = tenant.client.get(f"{PRODUCTS}filter-options/").data
    assert {c["name"] for c in data["categories"]} == {"Tea", "Oil"}
    assert [b["name"] for b in data["brands"]] == ["Acme"]
    assert {Decimal(rate) for rate in data["gst_rates"]} == {Decimal("5"), Decimal("12")}


def test_name_exact_finds_a_duplicate_ignoring_case(catalogue):
    tenant, *_ = catalogue
    assert _names(tenant.client.get(PRODUCTS, {"name_exact": "green tea"})) == {"Green Tea"}
    assert _names(tenant.client.get(PRODUCTS, {"name_exact": "green"})) == set()


def test_a_used_item_code_is_a_field_error_naming_the_other_item(catalogue):
    tenant, tea, *_ = catalogue
    body = {"name": "Another", "sku": "P9-TEA", "selling_price": "10", "gst_rate": "5"}
    resp = tenant.client.post(PRODUCTS, body, format="json")
    assert resp.status_code == 400
    assert "Green Tea" in str(resp.data)
    assert "already used" in str(resp.data)


def test_a_used_barcode_is_a_field_error_and_an_item_may_keep_its_own(catalogue):
    tenant, tea, oil, *_ = catalogue
    Product.objects.filter(pk=tea.pk).update(barcode="8901234567890")
    clash = tenant.client.post(
        PRODUCTS, {"name": "Clone", "sku": "P9-CL", "barcode": "8901234567890", "selling_price": "10", "gst_rate": "5"},
        format="json",
    )
    assert clash.status_code == 400 and "Green Tea" in str(clash.data)
    own = tenant.client.patch(f"{PRODUCTS}{tea.id}/", {"barcode": "8901234567890", "sku": "P9-TEA"}, format="json")
    assert own.status_code == 200, own.data


def test_deleting_a_used_item_deactivates_it_and_says_so(catalogue):
    tenant, tea, *_ = catalogue
    resp = tenant.client.delete(f"{PRODUCTS}{tea.id}/")
    assert resp.status_code == 200
    assert Product.objects.get(pk=tea.pk).status == Product.Status.INACTIVE
    assert "Inactive" in str(resp.data)


def test_deleting_an_unused_item_removes_it(tenant_a):
    fresh = make_product(tenant_a.company, sku="P9-NEW", name="Brand new")
    resp = tenant_a.client.delete(f"{PRODUCTS}{fresh.id}/")
    assert resp.status_code in (200, 204)
    assert not Product.objects.filter(pk=fresh.pk).exists()
