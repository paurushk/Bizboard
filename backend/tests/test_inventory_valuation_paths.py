"""WP-5 mutation survivors in InventoryValuationService.valuation: each read path, pinned by value.

Stock: 10 @ 80 then 10 @ 100 in the default godown. WAVG reads InventoryRunningCost, FIFO reads the
live cost layers; both must agree with a full replay, name the godown and item, divide value by
quantity, respect the warehouse / product filters, and fall back to a replay when the cached
quantity has drifted from the movements (CR-046).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from inventory.models import InventoryCostLayer, InventoryRunningCost, MovementType
from inventory.services import InventoryService, InventoryValuationService
from tests.conftest import add_stock, make_product

pytestmark = pytest.mark.django_db

D = Decimal


def _stock(tenant, method="WAVG"):
    # Cost layers are kept live only for a FIFO company; the running cost only for WAVG.
    tenant.company.inventory_valuation_method = method
    tenant.company.save(update_fields=["inventory_valuation_method"])
    product = make_product(tenant.company, sku="VAL-1", name="Valued Widget")
    other = make_product(tenant.company, sku="VAL-2", name="Other Widget")
    add_stock(tenant, product, "10", unit_cost="80")
    InventoryService.post_movement(
        company=tenant.company, product=product, movement_type=MovementType.PURCHASE,
        quantity=D("10"), unit_cost=D("100"), user=tenant.owner,
    )
    add_stock(tenant, other, "4", unit_cost="25")
    return product, other


def _row(rows, product):
    match = [r for r in rows if r["product"] == product.id]
    assert len(match) == 1, rows
    return match[0]


@pytest.mark.parametrize("method", ["WAVG", "FIFO"])
def test_live_path_rows_name_the_godown_and_item_and_divide_value_by_qty(tenant_a, method):
    product, other = _stock(tenant_a, method)
    rows = InventoryValuationService.valuation(tenant_a.company, method=method)
    row = _row(rows, product)
    assert row["qty"] == D("20")
    assert row["value"] == D("1800")
    assert row["unit_cost"] == D("90")
    assert row["product_name"] == "Valued Widget"
    assert row["warehouse_name"] and row["warehouse"]
    assert row["layers"] == []
    assert _row(rows, other)["value"] == D("100")
    # The live read agrees with a full replay as of today.
    replay = _row(InventoryValuationService.valuation(tenant_a.company, method=method, as_of="2099-12-31"), product)
    assert (replay["qty"], replay["value"]) == (D("20"), D("1800"))


@pytest.mark.parametrize("method", ["WAVG", "FIFO"])
def test_product_and_warehouse_filters(tenant_a, method):
    product, other = _stock(tenant_a, method)
    rows = InventoryValuationService.valuation(tenant_a.company, method=method, product=product)
    assert [r["product"] for r in rows] == [product.id]
    from inventory.models import Warehouse

    empty = Warehouse.objects.create(company=tenant_a.company, name="Empty godown")
    assert InventoryValuationService.valuation(tenant_a.company, method=method, warehouse=empty) == []


@pytest.mark.invariant_skip("inventory.running_cost_qty_matches_movements", reason="the test corrupts the running cost on purpose")
def test_wavg_drifted_running_cost_falls_back_to_the_movements(tenant_a):
    product, _ = _stock(tenant_a)
    InventoryRunningCost.objects.filter(company=tenant_a.company, product=product).update(qty=D("999"))
    row = _row(InventoryValuationService.valuation(tenant_a.company, method="WAVG"), product)
    assert row["qty"] == D("20")  # replayed from movements, not the drifted cache


def test_fifo_drifted_layers_fall_back_to_the_movements(tenant_a):
    product, _ = _stock(tenant_a, "FIFO")
    InventoryCostLayer.objects.filter(company=tenant_a.company, product=product).update(qty_remaining=D("1"))
    row = _row(InventoryValuationService.valuation(tenant_a.company, method="FIFO"), product)
    assert row["qty"] == D("20")
    assert row["value"] == D("1800")


def test_fifo_after_a_sale_keeps_the_newer_layer(tenant_a):
    product, _ = _stock(tenant_a, "FIFO")
    InventoryService.post_movement(
        company=tenant_a.company, product=product, movement_type=MovementType.SALE,
        quantity=D("15"), user=tenant_a.owner,
    )
    row = _row(InventoryValuationService.valuation(tenant_a.company, method="FIFO"), product)
    # FIFO: the 10 @ 80 are gone first, 5 of the 10 @ 100 remain.
    assert (row["qty"], row["value"], row["unit_cost"]) == (D("5"), D("500"), D("100"))


def test_unsupported_method_is_refused(tenant_a):
    from core.exceptions import BusinessRuleError

    with pytest.raises(BusinessRuleError):
        InventoryValuationService.valuation(tenant_a.company, method="LIFO")
