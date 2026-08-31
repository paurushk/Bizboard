from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone

from inventory.models import InventoryRunningCost, InventoryValuationSnapshot, MovementType
from inventory.services import InventoryService, InventoryValuationService
from tests.conftest import make_product


pytestmark = pytest.mark.django_db


def test_unit_cost_uses_running_cost_not_replay(tenant_a):
    product = make_product(tenant_a.company, sku="WAVG-RC")
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    for i in range(12):
        InventoryService.post_movement(
            company=tenant_a.company, warehouse=warehouse, product=product,
            movement_type=MovementType.PURCHASE, quantity="1", unit_cost=str(10 + i),
            user=tenant_a.owner,
        )
    assert InventoryRunningCost.objects.filter(company=tenant_a.company, product=product).exists()
    with patch.object(InventoryValuationService, "_replay", side_effect=AssertionError("replay")):
        cost = InventoryValuationService.unit_cost(tenant_a.company, product, warehouse)
    expected = sum(Decimal(10 + i) for i in range(12)) / Decimal("12")
    assert cost == expected


def test_flag_off_as_of_matches_created_at_replay(tenant_a):
    """Characterization: flag off uses insert time, not business date."""
    tenant_a.company.valuation_business_date_order = False
    tenant_a.company.save(update_fields=["valuation_business_date_order"])
    product = make_product(tenant_a.company, sku="CHAR-OFF")
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    today = timezone.localdate()
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=warehouse, product=product,
        movement_type=MovementType.PURCHASE, quantity="10", unit_cost="10",
        movement_date=today, user=tenant_a.owner,
    )
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=warehouse, product=product,
        movement_type=MovementType.SALE, quantity="5",
        movement_date=today + timedelta(days=5), user=tenant_a.owner,
    )
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=warehouse, product=product,
        movement_type=MovementType.PURCHASE, quantity="10", unit_cost="30",
        movement_date=today - timedelta(days=10), user=tenant_a.owner,
    )
    as_of = today + timedelta(days=5)
    rows = InventoryValuationService.valuation(tenant_a.company, as_of=as_of, product=product)
    assert len(rows) == 1
    # Insert order: 10@10, issue 5@10, add 10@30 → qty 15 value 350
    assert rows[0]["qty"] == Decimal("15")
    assert rows[0]["value"] == Decimal("350")


def test_flag_on_as_of_uses_business_date_order(tenant_a):
    tenant_a.company.valuation_business_date_order = True
    tenant_a.company.save(update_fields=["valuation_business_date_order"])
    product = make_product(tenant_a.company, sku="CHAR-ON")
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    today = timezone.localdate()
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=warehouse, product=product,
        movement_type=MovementType.PURCHASE, quantity="10", unit_cost="10",
        movement_date=today, user=tenant_a.owner,
    )
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=warehouse, product=product,
        movement_type=MovementType.SALE, quantity="5",
        movement_date=today + timedelta(days=5), user=tenant_a.owner,
    )
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=warehouse, product=product,
        movement_type=MovementType.PURCHASE, quantity="10", unit_cost="30",
        movement_date=today - timedelta(days=10), user=tenant_a.owner,
    )
    as_of = today + timedelta(days=5)
    rows = InventoryValuationService.valuation(tenant_a.company, as_of=as_of, product=product)
    assert len(rows) == 1
    # Business date: 10@30, then 10@10, then issue 5 at avg 20 → qty 15 value 300
    assert rows[0]["qty"] == Decimal("15")
    assert rows[0]["value"] == Decimal("300")
    assert rows[0]["unit_cost"] == Decimal("20")


def test_as_of_uses_snapshot_when_over_threshold(tenant_a, monkeypatch):
    monkeypatch.setattr(InventoryValuationService, "SNAPSHOT_THRESHOLD", 0)
    product = make_product(tenant_a.company, sku="SNAP-1")
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    today = timezone.localdate()
    period, period_end = InventoryValuationService._snapshot_period_for(today)
    InventoryValuationSnapshot.objects.create(
        company=tenant_a.company,
        period=period,
        warehouse=warehouse,
        product=product,
        batch=None,
        qty=Decimal("7"),
        value=Decimal("70"),
    )
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=warehouse, product=product,
        movement_type=MovementType.PURCHASE, quantity="3", unit_cost="10",
        movement_date=today, user=tenant_a.owner,
    )
    rows = InventoryValuationService.valuation(
        tenant_a.company, as_of=today, warehouse=warehouse, product=product,
    )
    assert len(rows) == 1
    # Snapshot 7@10 plus today's purchase 3@10 — full replay would only see qty 3.
    assert rows[0]["qty"] == Decimal("10")
    assert rows[0]["value"] == Decimal("100")
    assert period_end < today


def test_rebuild_running_cost_matches_balance(tenant_a):
    product = make_product(tenant_a.company, sku="REBUILD")
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=warehouse, product=product,
        movement_type=MovementType.PURCHASE, quantity="4", unit_cost="25",
        user=tenant_a.owner,
    )
    InventoryRunningCost.objects.filter(company=tenant_a.company).delete()
    call_command("rebuild_running_cost", company=tenant_a.company.pk)
    row = InventoryRunningCost.objects.get(company=tenant_a.company, product=product)
    assert row.qty == Decimal("4")
    assert row.value == Decimal("100")
    assert InventoryValuationService.unit_cost(tenant_a.company, product, warehouse) == Decimal("25")


def test_existing_company_flag_defaults_off(tenant_a):
    assert tenant_a.company.valuation_business_date_order is False
