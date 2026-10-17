"""INV-WP-03 — low-stock alert rows say whether they are per-godown or company-wide (review #7)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from inventory.models import MovementType, Warehouse, WarehouseReorderLevel
from inventory.services import InventoryService
from tests.conftest import make_product

pytestmark = pytest.mark.django_db

ALERTS = "/api/v1/inventory/alerts/"


def _stock(tenant, product, warehouse, qty):
    InventoryService.post_movement(
        company=tenant.company, product=product, movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal(qty), unit_cost=Decimal("10"), user=tenant.owner, warehouse=warehouse,
    )


def test_company_wide_and_godown_rows_are_labelled(tenant_a):
    main = InventoryService.default_warehouse(tenant_a.company)
    north = Warehouse.objects.create(company=tenant_a.company, name="North", code="NR")

    company_wide = make_product(tenant_a.company, sku="LS-ALL", name="Tea", reorder_level="10")
    _stock(tenant_a, company_wide, main, "3")

    per_godown = make_product(tenant_a.company, sku="LS-NR", name="Rice", reorder_level="0")
    _stock(tenant_a, per_godown, north, "2")
    WarehouseReorderLevel.objects.create(
        company=tenant_a.company, warehouse=north, product=per_godown, reorder_level=Decimal("8"),
    )

    resp = tenant_a.client.get(ALERTS)
    assert resp.status_code == 200, resp.data
    by_sku = {row["sku"]: row for row in resp.data["items"]}
    assert by_sku["LS-ALL"]["is_warehouse_specific"] is False
    assert by_sku["LS-NR"]["is_warehouse_specific"] is True
    assert by_sku["LS-NR"]["warehouse_name"] == "North"
