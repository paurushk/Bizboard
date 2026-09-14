"""Persona Journey — Godown Custodian Physical Inventory Verification & Stock Audit.

Validates:
1. Physical Stock Count Session Creation:
   - Godown custodian creates StockCountSession in DRAFT for a specific warehouse.
   - Automatic snapshot of existing on-hand balances for products in the warehouse.
2. Cycle Count Entry & Variance Calculation:
   - Entering physical counts for each line item (detecting both shortage and surplus).
   - Status transition from DRAFT to COUNTED once all physical quantities are entered.
3. Post Count & Automatic Stock Adjustment:
   - Posting the count session applies adjustments to inventory balances.
   - Invariant check verifies physical on-hand matches updated balance records.
   - Movements recorded with audit reference 'stock_count'.
4. Role Boundaries:
   - Counter Clerk / Sales Staff without inventory management capability is denied access (HTTP 403).
5. Invariants:
   - assert_all_invariants(company) holds clean without discrepancy.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.invariants import assert_all_invariants
from inventory.models import MovementType, StockBalance, StockCountSession, StockMovement
from inventory.services import InventoryService
from tests.personas.fixtures import seed_archetype

pytestmark = pytest.mark.django_db


def test_pj_custodian_physical_stock_count_and_adjustments():
    """P4 Godown Custodian: Physical count session, shortage/surplus adjustments, and role boundary."""
    ns = seed_archetype("wholesale")
    company = ns.company
    gc = ns.godown_client
    sc = ns.sales_client
    wh_main = ns.warehouses[0]

    plain_products = [p for p in ns.products if not p.track_batch][:2]
    p1, p2 = plain_products[0], plain_products[1]

    # 1. Inward initial stock to warehouse
    InventoryService.post_movement(
        company=company,
        product=p1,
        movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("100.000"),
        unit_cost=Decimal("50.00"),
        user=ns.owner,
        warehouse=wh_main,
    )
    InventoryService.post_movement(
        company=company,
        product=p2,
        movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("50.000"),
        unit_cost=Decimal("80.00"),
        user=ns.owner,
        warehouse=wh_main,
    )

    assert InventoryService.available_quantity(company, p1, warehouse=wh_main) == Decimal("100.000")
    assert InventoryService.available_quantity(company, p2, warehouse=wh_main) == Decimal("50.000")

    # 2. Custodian creates Stock Count Session
    create_resp = gc.post(
        "/api/v1/inventory/stock-counts/",
        {
            "warehouse": wh_main.id,
            "notes": "Q1 Godown Physical Inventory Audit",
        },
        format="json",
    )
    assert create_resp.status_code == 201, create_resp.data
    session_id = create_resp.data["id"]

    session = StockCountSession.objects.get(pk=session_id)
    assert session.status == StockCountSession.Status.DRAFT
    assert session.lines.count() >= 2

    # Find the line IDs for p1 and p2
    line_p1 = session.lines.get(product=p1)
    line_p2 = session.lines.get(product=p2)
    assert line_p1.system_qty == Decimal("100.000")
    assert line_p2.system_qty == Decimal("50.000")

    # 3. Custodian enters physical counts:
    # p1 has shortage of 6 (counted 94)
    # p2 has surplus of 3 (counted 53)
    update_lines = []
    for line in session.lines.all():
        if line.product_id == p1.id:
            update_lines.append({"id": line.id, "counted_qty": "94.000"})
        elif line.product_id == p2.id:
            update_lines.append({"id": line.id, "counted_qty": "53.000"})
        else:
            update_lines.append({"id": line.id, "counted_qty": str(line.system_qty)})

    patch_resp = gc.patch(
        f"/api/v1/inventory/stock-counts/{session_id}/",
        {"lines": update_lines},
        format="json",
    )
    assert patch_resp.status_code == 200, patch_resp.data
    session.refresh_from_db()
    assert session.status == StockCountSession.Status.COUNTED

    # 4. Custodian posts the count session
    post_resp = gc.post(f"/api/v1/inventory/stock-counts/{session_id}/post/")
    assert post_resp.status_code == 200, post_resp.data
    session.refresh_from_db()
    assert session.status == StockCountSession.Status.POSTED

    # 5. Verify updated inventory balances
    bal1 = StockBalance.objects.get(company=company, product=p1, warehouse=wh_main)
    bal2 = StockBalance.objects.get(company=company, product=p2, warehouse=wh_main)
    assert bal1.on_hand == Decimal("94.000")
    assert bal2.on_hand == Decimal("53.000")

    # Verify audit trail movements
    adj_movements = StockMovement.objects.filter(
        company=company,
        reference_type="stock_count",
        reference_id=str(session_id),
    )
    assert adj_movements.count() == 2

    # 6. Role boundary: Clerk denied permission to initiate stock count
    clerk_denied = sc.post(
        "/api/v1/inventory/stock-counts/",
        {
            "warehouse": wh_main.id,
            "notes": "Clerk should not count stock",
        },
        format="json",
    )
    assert clerk_denied.status_code == 403

    # Invariant sweep is clean
    assert_all_invariants(company)
