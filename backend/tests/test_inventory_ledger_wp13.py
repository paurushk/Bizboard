"""INV-WP-13 — the item ledger: every movement, filterable, with a running balance (review #15)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from inventory.models import MovementType, Warehouse
from inventory.services import InventoryService
from tests.conftest import make_product

pytestmark = pytest.mark.django_db

LEDGER = "/api/v1/inventory/movements/"
TODAY = date.today()


def _move(tenant, product, kind, qty, day, warehouse=None, cost=None, reason=""):
    return InventoryService.post_movement(
        company=tenant.company, product=product, movement_type=kind, quantity=Decimal(qty),
        unit_cost=Decimal(cost) if cost else None, user=tenant.owner, warehouse=warehouse,
        movement_date=day, reason=reason,
    )


def _sales_user(tenant):
    """A salesperson who may see stock but not what it cost."""
    from accounts.models import CompanyUser, User
    from rest_framework.test import APIClient

    user = User.objects.create_user(email="sales-wp13@alpha.test", password="StrongPass123!")
    CompanyUser.objects.create(
        company=tenant.company, user=user, role=CompanyUser.Role.SALES_STAFF, can_create_sales=True,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _rows(resp):
    assert resp.status_code == 200, resp.data
    return resp.data["results"] if isinstance(resp.data, dict) and "results" in resp.data else resp.data


@pytest.fixture
def tea(tenant_a):
    product = make_product(tenant_a.company, sku="LG-1", name="Tea")
    _move(tenant_a, product, MovementType.OPENING_STOCK, "100", TODAY - timedelta(days=10), cost="50")
    _move(tenant_a, product, MovementType.ADJUSTMENT, "-5", TODAY - timedelta(days=5), reason="Damaged")
    _move(tenant_a, product, MovementType.ADJUSTMENT, "2", TODAY - timedelta(days=1), reason="Found")
    return product


def test_one_item_shows_a_running_balance_newest_first(tenant_a, tea):
    rows = _rows(tenant_a.client.get(LEDGER, {"product": tea.id}))
    assert [Decimal(str(r["quantity"])) for r in rows] == [Decimal("2"), Decimal("-5"), Decimal("100")]
    assert [Decimal(str(r["running_balance"])) for r in rows] == [Decimal("97"), Decimal("95"), Decimal("100")]
    assert rows[0]["movement_type_label"] and rows[0]["product_name"] == "Tea" and rows[0]["reason"] == "Found"


def test_a_date_filter_keeps_the_balance_honest_by_counting_what_came_before(tenant_a, tea):
    rows = _rows(tenant_a.client.get(LEDGER, {"product": tea.id, "date_from": str(TODAY - timedelta(days=6))}))
    assert [Decimal(str(r["running_balance"])) for r in rows] == [Decimal("97"), Decimal("95")]


def test_without_one_item_there_is_no_balance_to_show(tenant_a, tea):
    rows = _rows(tenant_a.client.get(LEDGER))
    assert rows and all(r["running_balance"] is None for r in rows)


def test_filters_narrow_by_type_godown_dates_and_text(tenant_a, tea):
    other_wh = Warehouse.objects.create(company=tenant_a.company, name="North", code="NR")
    rice = make_product(tenant_a.company, sku="LG-2", name="Rice")
    _move(tenant_a, rice, MovementType.OPENING_STOCK, "10", TODAY - timedelta(days=3), warehouse=other_wh, cost="20")

    adjustments = _rows(tenant_a.client.get(LEDGER, {"movement_type": "ADJUSTMENT"}))
    assert {r["reason"] for r in adjustments} == {"Damaged", "Found"}
    assert {r["product_name"] for r in _rows(tenant_a.client.get(LEDGER, {"warehouse": other_wh.id}))} == {"Rice"}
    assert {r["reason"] for r in _rows(tenant_a.client.get(LEDGER, {"product": tea.id, "date_to": str(TODAY - timedelta(days=4))}))} == {"", "Damaged"}
    assert {r["product_name"] for r in _rows(tenant_a.client.get(LEDGER, {"search": "rice"}))} == {"Rice"}
    assert {r["reason"] for r in _rows(tenant_a.client.get(LEDGER, {"search": "damag"}))} == {"Damaged"}


def test_it_is_paged(tenant_a, tea):
    resp = tenant_a.client.get(LEDGER, {"product": tea.id, "page_size": 2})
    assert resp.status_code == 200
    assert resp.data["count"] == 3 and len(resp.data["results"]) == 2


def test_what_an_item_cost_is_for_the_owner_not_for_a_sales_user(tenant_a, tea):
    owner_rows = _rows(tenant_a.client.get(LEDGER, {"product": tea.id}))
    assert any(r["unit_cost"] is not None for r in owner_rows)
    staff_rows = _rows(_sales_user(tenant_a).get(LEDGER, {"product": tea.id}))
    assert staff_rows and all(r["unit_cost"] is None for r in staff_rows)


def test_a_viewer_gets_nothing(tenant_a, tea):
    from accounts.models import CompanyUser, User
    from rest_framework.test import APIClient

    viewer = User.objects.create_user(email="viewer-wp13@alpha.test", password="StrongPass123!")
    CompanyUser.objects.create(company=tenant_a.company, user=viewer, role=CompanyUser.Role.VIEWER)
    client = APIClient()
    client.force_authenticate(user=viewer)
    assert client.get(LEDGER).status_code == 403
    assert client.get(LEDGER + "export/").status_code == 403


def test_the_csv_has_the_whole_story_and_does_not_run_formulas(tenant_a):
    product = make_product(tenant_a.company, sku="LG-X", name="=HYPERLINK(\"http://x\")")
    _move(tenant_a, product, MovementType.OPENING_STOCK, "5", TODAY - timedelta(days=2), cost="10", reason="+boot")
    resp = tenant_a.client.get(LEDGER + "export/")
    assert resp.status_code == 200 and resp["Content-Type"].startswith("text/csv")
    body = b"".join(resp.streaming_content).decode()
    header = body.splitlines()[0]
    assert header == "Date,Item,SKU,Godown,Batch,Type,Quantity,Unit cost,Reason,Reference,Reference id,By"
    assert "'=HYPERLINK" in body and ",'+boot," in body


def test_the_csv_leaves_out_cost_for_a_sales_user(tenant_a, tea):
    resp = _sales_user(tenant_a).get(LEDGER + "export/")
    assert resp.status_code == 200
    body = b"".join(resp.streaming_content).decode()
    assert "Unit cost" not in body.splitlines()[0]
