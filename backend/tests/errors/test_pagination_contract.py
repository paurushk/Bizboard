"""§H8 — pagination correctness (docs/FREEZE_SCOPE_COVERAGE.md GAP #7).

DefaultPagination (core/pagination.py): page_size 50, max_page_size 200,
`?page_size=` override, and a primary-key tie-break appended to every list
queryset so paging is stable even when the view's ordering key is not unique.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from masters.models import Product

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/products/"


def _seed(company, n):
    # identical created_at within the tick -> only the pk tie-break keeps paging stable
    Product.objects.bulk_create(
        Product(
            company=company, name=f"Pager Item {i:03d}", sku=f"PGR-{i:03d}",
            gst_rate=Decimal("18"), purchase_price=Decimal("10"),
            selling_price=Decimal("20"), reorder_level=Decimal("0"),
        )
        for i in range(n)
    )


def test_page_size_override_is_capped_at_max(tenant_a):
    _seed(tenant_a.company, 60)
    resp = tenant_a.client.get(LIST_URL, {"page_size": 9999})
    assert resp.status_code == 200
    assert len(resp.data["results"]) <= 200  # max_page_size, not 9999
    assert resp.data["count"] == 60


def test_default_page_size_and_total_count(tenant_a):
    _seed(tenant_a.company, 60)
    resp = tenant_a.client.get(LIST_URL)
    assert resp.status_code == 200
    assert resp.data["count"] == 60
    assert len(resp.data["results"]) == 50  # DefaultPagination.page_size
    assert resp.data["next"] and not resp.data["previous"]


def test_paging_is_stable_no_drops_or_dupes(tenant_a):
    _seed(tenant_a.company, 60)
    seen: list[int] = []
    page = 1
    while True:
        resp = tenant_a.client.get(LIST_URL, {"page": page, "page_size": 25})
        assert resp.status_code == 200, resp.data
        ids = [row["id"] for row in resp.data["results"]]
        seen.extend(ids)
        if not resp.data["next"]:
            break
        page += 1
        assert page < 20, "pagination did not terminate"

    assert len(seen) == 60, f"expected 60 rows across pages, got {len(seen)}"
    assert len(set(seen)) == 60, "a row was repeated across page boundaries"


def test_out_of_range_page_is_404_not_a_silent_empty(tenant_a):
    _seed(tenant_a.company, 5)
    resp = tenant_a.client.get(LIST_URL, {"page": 99})
    assert resp.status_code == 404
