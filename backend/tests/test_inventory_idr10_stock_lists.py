"""INV-IDR-10 - the grouped stock list is computed on the server and agrees with the flat rows."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

import pytest

from inventory.models import Warehouse
from inventory.services import InventoryService
from tests.conftest import add_stock, make_product

pytestmark = pytest.mark.django_db

FLAT = "/api/v1/inventory/balances/"
GROUPED = "/api/v1/inventory/balances/by-product/"


def _rows(data):
    return data["results"] if isinstance(data, dict) and "results" in data else data


def _seed(tenant):
    """Three items over two godowns; one item out of stock; one with a negative balance."""
    main = InventoryService.default_warehouse(tenant.company)
    north = Warehouse.objects.create(company=tenant.company, name="North", code="N10")
    a = make_product(tenant.company, sku="L10-A", name="Apple")
    b = make_product(tenant.company, sku="L10-B", name="Banana")
    c = make_product(tenant.company, sku="L10-C", name="Cherry")
    add_stock(tenant, a, "10")
    add_stock(tenant, b, "4")
    InventoryService.post_movement(
        company=tenant.company, warehouse=north, product=a, movement_type="ADJUSTMENT",
        quantity=Decimal("6"), reason="seed", reference_type="manual_adjustment", user=None,
    )
    add_stock(tenant, c, "1")
    InventoryService.post_movement(
        company=tenant.company, warehouse=main, product=c, movement_type="ADJUSTMENT",
        quantity=Decimal("-1"), reason="seed", reference_type="manual_adjustment", user=None,
    )
    return main, north, a, b, c


def test_grouped_totals_equal_the_sum_of_the_flat_rows(tenant_a):
    _seed(tenant_a)
    flat = defaultdict(lambda: [Decimal("0"), Decimal("0")])
    for row in _rows(tenant_a.client.get(FLAT, {"page_size": 200}).data):
        flat[row["product"]][0] += Decimal(str(row["on_hand"]))
        flat[row["product"]][1] += Decimal(str(row["available"]))
    grouped = tenant_a.client.get(GROUPED).data
    got = {r["product"]: (Decimal(str(r["on_hand"])), Decimal(str(r["available"]))) for r in _rows(grouped)}
    assert got == {k: (v[0], v[1]) for k, v in flat.items()}


def test_grouped_rows_name_the_item_and_count_lots_and_carry_summary(tenant_a):
    _main, _north, a, _b, _c = _seed(tenant_a)
    data = tenant_a.client.get(GROUPED).data
    by_id = {r["product"]: r for r in _rows(data)}
    assert by_id[a.id]["product_name"] == "Apple"
    assert by_id[a.id]["sku"] == "L10-A"
    assert by_id[a.id]["lots"] >= 2  # main + north
    summary = data["summary"]
    assert summary["items"] == 3
    assert summary["items_in_stock"] == 2
    assert summary["items_out"] == 1


def test_grouped_list_is_paged_and_ordered(tenant_a):
    _seed(tenant_a)
    first = tenant_a.client.get(GROUPED, {"page_size": 2}).data
    assert len(_rows(first)) == 2
    assert first["count"] == 3
    names = [r["product_name"] for r in _rows(first)]
    assert names == sorted(names)
    second = tenant_a.client.get(GROUPED, {"page_size": 2, "page": 2}).data
    assert [r["product_name"] for r in _rows(second)] == ["Cherry"]
    by_stock = tenant_a.client.get(GROUPED, {"ordering": "-available"}).data
    quantities = [Decimal(str(r["available"])) for r in _rows(by_stock)]
    assert quantities == sorted(quantities, reverse=True)


def test_grouped_godown_filter_and_negative_filter(tenant_a):
    main, north, a, _b, c = _seed(tenant_a)
    only_north = _rows(tenant_a.client.get(GROUPED, {"warehouse": north.id}).data)
    assert [r["product"] for r in only_north] == [a.id]
    assert Decimal(str(only_north[0]["on_hand"])) == Decimal("6")
    out = _rows(tenant_a.client.get(GROUPED, {"negative": "1"}).data)
    assert [r["product"] for r in out] == [c.id]


def test_flat_list_negative_filter_keeps_only_empty_rows(tenant_a):
    _main, _north, _a, _b, c = _seed(tenant_a)
    rows = _rows(tenant_a.client.get(FLAT, {"negative": "1", "page_size": 200}).data)
    assert rows and {r["product"] for r in rows} == {c.id}


def test_grouped_search_is_the_same_filter_as_the_flat_list(tenant_a):
    _main, _north, a, _b, _c = _seed(tenant_a)
    rows = _rows(tenant_a.client.get(GROUPED, {"q": "Apple"}).data)
    assert [r["product"] for r in rows] == [a.id]


def test_other_company_rows_never_appear(tenant_a, tenant_b):
    _seed(tenant_a)
    other = make_product(tenant_b.company, sku="L10-X", name="Other")
    add_stock(tenant_b, other, "5")
    ids = {r["product"] for r in _rows(tenant_a.client.get(GROUPED).data)}
    assert other.id not in ids


def _csv(response):
    return b"".join(response.streaming_content).decode()


def test_stock_csv_follows_the_page_filters(tenant_a):
    _main, north, _a, _b, _c = _seed(tenant_a)
    everything = _csv(tenant_a.client.get("/api/v1/exports/inventory/"))
    assert "Apple" in everything and "Banana" in everything
    searched = _csv(tenant_a.client.get("/api/v1/exports/inventory/", {"q": "Apple"}))
    assert "Apple" in searched and "Banana" not in searched
    in_north = _csv(tenant_a.client.get("/api/v1/exports/inventory/", {"warehouse": north.id}))
    assert "Apple" in in_north and "Banana" not in in_north
