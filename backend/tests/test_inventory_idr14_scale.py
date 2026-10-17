"""INV-IDR-14 - the stock lists stay quick and light with a big catalogue (10,000 items x 3 godowns).

Targets from the plan: under 1.5 s to the first rows and under 300 KB per request. The numbers are
printed so a slow run can be compared; the assertions are a generous ceiling so a different machine
does not make the test flaky. Balances are written straight to the table (no movements), so the
movement-sum invariant is switched off for this test.
"""

from __future__ import annotations

import json
import time
from decimal import Decimal

import pytest

from inventory.models import StockBalance, Warehouse
from inventory.services import InventoryService
from masters.models import Category, Product

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.no_invariant_check]

ITEMS = 10_000
SECONDS = 4.0  # ceiling; the plan's target is 1.5 s on the production database
KILOBYTES = 300


@pytest.fixture
def big_catalogue(tenant_a):
    company = tenant_a.company
    main = InventoryService.default_warehouse(company)
    others = [Warehouse.objects.create(company=company, name=f"G{i}", code=f"SC{i}") for i in range(2)]
    category = Category.objects.create(company=company, name="Bulk")
    Product.objects.bulk_create([
        Product(
            company=company, name=f"Item {i:05d}", sku=f"SC-{i:05d}", gst_rate=Decimal("18"),
            purchase_price=Decimal("10"), selling_price=Decimal("15"), category=category,
        )
        for i in range(ITEMS)
    ], batch_size=2000)
    ids = list(Product.objects.filter(company=company, sku__startswith="SC-").values_list("id", flat=True))
    StockBalance.objects.bulk_create([
        StockBalance(company=company, warehouse=warehouse, product_id=pid, on_hand=Decimal(i % 7), reserved=Decimal(0))
        for i, pid in enumerate(ids)
        for warehouse in (main, *others)
    ], batch_size=2000)
    return tenant_a


def _timed(client, url, params=None):
    start = time.perf_counter()
    resp = client.get(url, params or {})
    elapsed = time.perf_counter() - start
    assert resp.status_code == 200, (url, resp.status_code)
    kilobytes = len(json.dumps(resp.data, default=str)) / 1024
    print(f"\n[scale] {url} {params or ''}: {elapsed:.2f}s, {kilobytes:.0f} KB")
    return elapsed, kilobytes


LISTS = [
    ("/api/v1/inventory/balances/by-product/", {"page_size": 100}),
    ("/api/v1/inventory/balances/by-product/", {"page_size": 100, "ordering": "-available", "negative": "1"}),
    ("/api/v1/inventory/balances/by-product/", {"page_size": 100, "q": "Item 0001"}),
    ("/api/v1/products/", {"page_size": 50}),
    ("/api/v1/products/", {"page_size": 50, "stock_status": "out"}),
    ("/api/v1/products/", {"page_size": 50, "stock_status": "in"}),
    ("/api/v1/products/filter-options/", {}),
]


def test_the_big_lists_come_back_quickly_and_small(big_catalogue):
    """One seeding for every list (10,000 items is slow to build). A first request warms the process."""
    client = big_catalogue.client
    client.get("/api/v1/products/filter-options/")
    slow = []
    for url, params in LISTS:
        elapsed, kilobytes = _timed(client, url, params)
        if elapsed >= SECONDS or kilobytes >= KILOBYTES:
            slow.append((url, params, round(elapsed, 2), round(kilobytes)))
    assert not slow, slow
    product = Product.objects.filter(company=big_catalogue.company, sku="SC-00042").first()
    elapsed, kilobytes = _timed(client, "/api/v1/inventory/balances/", {"product": product.id})
    assert elapsed < SECONDS and kilobytes < 20
