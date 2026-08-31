"""C-01: stock count post is idempotent; qty drift is a 409 choice."""

from decimal import Decimal

import pytest

from inventory.models import MovementType, StockBalance, StockCountSession, StockMovement
from inventory.services import InventoryService
from tests.conftest import add_stock, make_product

pytestmark = pytest.mark.django_db


def _counted_session(tenant, product, counted="7"):
    add_stock(tenant, product, "10")
    warehouse = InventoryService.default_warehouse(tenant.company)
    session = tenant.client.post(
        "/api/v1/inventory/stock-counts/",
        {"warehouse": warehouse.id},
        format="json",
    )
    assert session.status_code == 201, session.data
    line = (session.data.get("lines") or [])[0]
    patch = tenant.client.patch(
        f"/api/v1/inventory/stock-counts/{session.data['id']}/",
        {"lines": [{"id": line["id"], "counted_qty": counted}]},
        format="json",
    )
    assert patch.status_code == 200, patch.data
    return session.data["id"], warehouse, line


def test_stock_count_double_post_is_idempotent(tenant_a):
    product = make_product(tenant_a.company, sku="C01-ID")
    sid, warehouse, _ = _counted_session(tenant_a, product)
    first = tenant_a.client.post(f"/api/v1/inventory/stock-counts/{sid}/post/")
    assert first.status_code == 200, first.data
    second = tenant_a.client.post(f"/api/v1/inventory/stock-counts/{sid}/post/")
    assert second.status_code == 200, second.data
    moves = StockMovement.objects.filter(
        product=product, movement_type=MovementType.ADJUSTMENT, reason="STOCK_COUNT",
    )
    assert moves.count() == 1
    assert StockBalance.objects.get(product=product, warehouse=warehouse, batch__isnull=True).on_hand == Decimal("7")


def test_stock_count_qty_drift_is_409_until_choice(tenant_a):
    product = make_product(tenant_a.company, sku="C01-CF")
    sid, warehouse, _line = _counted_session(tenant_a, product, counted="9")
    InventoryService.post_movement(
        company=tenant_a.company,
        product=product,
        movement_type=MovementType.ADJUSTMENT,
        quantity=Decimal("2"),
        reason="OTHER",
        user=tenant_a.owner,
        warehouse=warehouse,
    )
    blocked = tenant_a.client.post(f"/api/v1/inventory/stock-counts/{sid}/post/")
    assert blocked.status_code == 409, blocked.data
    err = blocked.data.get("error") or blocked.data
    assert err.get("code") == "STOCK_COUNT_CONFLICT"
    kept = tenant_a.client.post(
        f"/api/v1/inventory/stock-counts/{sid}/post/",
        {"resolve_conflicts": "KEEP_LOCAL"},
        format="json",
    )
    assert kept.status_code == 200, kept.data
    assert StockCountSession.objects.get(pk=sid).status == StockCountSession.Status.POSTED
    assert StockBalance.objects.get(product=product, warehouse=warehouse, batch__isnull=True).on_hand == Decimal("9")
