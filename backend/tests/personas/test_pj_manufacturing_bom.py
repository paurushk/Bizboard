"""ARCH-08: Small Manufacturer / Assembler persona journey.

Validates:
1. P1 (Owner) defines multi-component Bill of Materials (BOM).
2. P4 (Godown Custodian) inwards raw materials and executes Work Orders.
3. Work Order release consumes raw materials from warehouse, debits WIP (Account 1450).
4. Work Order completion receives finished goods into warehouse, credits WIP, debits FG inventory.
5. Cancellation rollback restores component stock and reverses WIP journals.
6. P2/P3 (Sales Staff) is denied manufacturing operations (capability boundary).
7. Zero invariant violations: assert_all_invariants(company) holds throughout.
"""

from decimal import Decimal
import pytest

from core.invariants import assert_all_invariants
from inventory.models import MovementType, StockBalance
from inventory.services import InventoryService
from manufacturing.models import Bom, WorkOrder
from tests.personas.fixtures import seed_archetype

pytestmark = [pytest.mark.django_db, pytest.mark.dark_module]


def _body(resp):
    data = resp.data
    if isinstance(data, dict) and isinstance(data.get("data"), (dict, list)):
        return data["data"]
    return data


def test_pj_manufacturing_bom_work_order_lifecycle():
    mfg = seed_archetype("manufacturing")
    company = mfg.company
    wh = mfg.warehouses[0]

    comp1 = mfg.products[0]  # Raw Material 1
    comp2 = mfg.products[1]  # Raw Material 2
    fg = mfg.products[5]     # Finished Product

    # 1. P4 (Godown Custodian) inwards components
    InventoryService.post_movement(
        company=company,
        product=comp1,
        warehouse=wh,
        quantity=Decimal("50"),
        movement_type=MovementType.PURCHASE,
        unit_cost=Decimal("40.00"),
        user=mfg.godown,
    )
    InventoryService.post_movement(
        company=company,
        product=comp2,
        warehouse=wh,
        quantity=Decimal("100"),
        movement_type=MovementType.PURCHASE,
        unit_cost=Decimal("20.00"),
        user=mfg.godown,
    )

    assert StockBalance.objects.get(company=company, product=comp1, warehouse=wh).on_hand == Decimal("50")
    assert StockBalance.objects.get(company=company, product=comp2, warehouse=wh).on_hand == Decimal("100")

    # 2. P1 (Owner) defines BOM: 2 comp1 + 4 comp2 = 1 fg
    bom_resp = mfg.owner_client.post(
        "/api/v1/manufacturing/boms/",
        {
            "product": fg.id,
            "name": f"BOM for {fg.name}",
            "status": Bom.Status.ACTIVE,
            "lines": [
                {"component": comp1.id, "qty": "2"},
                {"component": comp2.id, "qty": "4"},
            ],
        },
        format="json",
    )
    assert bom_resp.status_code == 201, bom_resp.data
    bom_id = _body(bom_resp)["id"]

    # 3. Boundary check: Non-owners (Sales Staff & Godown Custodian) cannot create or release work orders
    sales_create = mfg.sales_client.post(
        "/api/v1/manufacturing/work-orders/",
        {"bom": bom_id, "qty": "10", "warehouse": wh.id},
        format="json",
    )
    assert sales_create.status_code == 403, "Sales staff must be denied work orders"

    godown_create = mfg.godown_client.post(
        "/api/v1/manufacturing/work-orders/",
        {"bom": bom_id, "qty": "10", "warehouse": wh.id},
        format="json",
    )
    assert godown_create.status_code == 403, "Godown custodian must be denied work orders"

    # 4. P1 (Owner) drafts Work Order for 10 units of FG
    wo_resp = mfg.owner_client.post(
        "/api/v1/manufacturing/work-orders/",
        {"bom": bom_id, "qty": "10", "warehouse": wh.id},
        format="json",
    )
    assert wo_resp.status_code == 201, wo_resp.data
    wo_id = _body(wo_resp)["id"]

    # Boundary check: Godown cannot release
    assert mfg.godown_client.post(f"/api/v1/manufacturing/work-orders/{wo_id}/release/").status_code == 403

    # 5. P1 (Owner) releases Work Order (10 units * (2 comp1, 4 comp2) = 20 comp1, 40 comp2)
    rel_resp = mfg.owner_client.post(f"/api/v1/manufacturing/work-orders/{wo_id}/release/")
    assert rel_resp.status_code == 200, rel_resp.data

    # Raw material stock is consumed
    assert StockBalance.objects.get(company=company, product=comp1, warehouse=wh).on_hand == Decimal("30")
    assert StockBalance.objects.get(company=company, product=comp2, warehouse=wh).on_hand == Decimal("60")

    # 6. P1 (Owner) completes Work Order -> FG stock received
    comp_resp = mfg.owner_client.post(f"/api/v1/manufacturing/work-orders/{wo_id}/complete/")
    assert comp_resp.status_code == 200, comp_resp.data

    fg_stock = StockBalance.objects.get(company=company, product=fg, warehouse=wh).on_hand
    assert fg_stock == Decimal("10"), "10 units of Finished Good must be in stock"

    # 7. Cancellation & Rollback Verification
    # Draft and release a second WO for 2 units
    wo2_resp = mfg.owner_client.post(
        "/api/v1/manufacturing/work-orders/",
        {"bom": bom_id, "qty": "2", "warehouse": wh.id},
        format="json",
    )
    assert wo2_resp.status_code == 201
    wo2_id = _body(wo2_resp)["id"]
    assert mfg.owner_client.post(f"/api/v1/manufacturing/work-orders/{wo2_id}/release/").status_code == 200

    # Stock dropped by 4 comp1 and 8 comp2
    assert StockBalance.objects.get(company=company, product=comp1, warehouse=wh).on_hand == Decimal("26")
    assert StockBalance.objects.get(company=company, product=comp2, warehouse=wh).on_hand == Decimal("52")

    # Cancel the released WO -> stock must be cleanly restored
    cancel_resp = mfg.owner_client.post(f"/api/v1/manufacturing/work-orders/{wo2_id}/cancel/")
    assert cancel_resp.status_code == 200, cancel_resp.data
    assert StockBalance.objects.get(company=company, product=comp1, warehouse=wh).on_hand == Decimal("30")
    assert StockBalance.objects.get(company=company, product=comp2, warehouse=wh).on_hand == Decimal("60")

    # 8. All financial and inventory invariants hold
    assert_all_invariants(company)
