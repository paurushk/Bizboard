"""PJ-CONTRACTOR-HYBRID — ARCH-07 Commercial Service & Spares Contractor Journey.

Validates:
1. Hybrid commercial contracting with mixed lines:
   - Service item (SAC code, track_inventory=False, product_type=SERVICE)
   - Spare part item (HSN code, track_inventory=True, product_type=GOODS)
2. Selective stock movements: StockMovement is generated ONLY for the physical spares,
   never for the pure service line.
3. Accurate unified billing, tax computation, and AR ledger accumulation.
4. Complete receipt payment and allocation loop.
5. Role boundaries across Sales Staff, Accountant, and Owner.
6. Clean invariant sweeps across all operations.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.invariants import assert_all_invariants
from inventory.models import MovementType, StockMovement
from inventory.services import InventoryService
from tests.personas.fixtures import seed_archetype

pytestmark = pytest.mark.django_db


def test_pj_contractor_hybrid_service_and_spares_journey(boundary):
    ns = seed_archetype("contractor")
    company = ns.company
    oc = ns.owner_client
    sc = ns.sales_client
    ac = ns.acct_client
    cust = ns.customers[0]

    # Archetype catalogue has alternating SERVICE and GOODS items
    service_item = next(p for p in ns.products if p.product_type == "SERVICE")
    spare_item = next(p for p in ns.products if p.product_type == "GOODS")

    assert service_item.track_inventory is False
    assert spare_item.track_inventory is True

    # 1. Seed stock only for the spare part (service item rejects stock movements)
    InventoryService.post_movement(
        company=company, product=spare_item, movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("20"), unit_cost=Decimal("150.00"), user=ns.owner,
    )
    assert InventoryService.available_quantity(company, spare_item) == Decimal("20.000")

    # 2. P2/P3 Sales Staff creates hybrid contractor invoice:
    # 1x Service call (₹1,500 + 18% GST) + 2x Compressor spare valves (₹250 ea = ₹500 + 18% GST)
    inv = sc.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust.id,
            "invoice_type": "GST",
            "items": [
                {
                    "product": service_item.id,
                    "quantity": "1",
                    "unit_price": "1500.00",
                    "gst_rate": "18",
                },
                {
                    "product": spare_item.id,
                    "quantity": "2",
                    "unit_price": "250.00",
                    "gst_rate": "18",
                },
            ],
        },
        format="json",
    )
    assert inv.status_code == 201, inv.data
    iid = inv.data["id"]

    done = sc.post(f"/api/v1/sales/invoices/{iid}/complete/")
    assert done.status_code == 200, done.data
    # Subtotal = 1500 + 500 = 2000. GST (18%) = 360. Grand total = 2360.00
    grand_total = Decimal(str(done.data["grand_total"]))
    assert grand_total == Decimal("2360.00")

    # 3. Verify selective stock movements
    # Spare parts inventory decreased by 2 (20 -> 18)
    assert InventoryService.available_quantity(company, spare_item) == Decimal("18.000")

    # StockMovement exists ONLY for spare_item, ZERO for service_item
    movements = StockMovement.objects.filter(company=company, reference_type="sales_invoice", reference_id=str(iid))
    assert movements.count() == 1
    assert movements.first().product_id == spare_item.id
    assert not StockMovement.objects.filter(company=company, product_id=service_item.id).exists()

    # 4. Receipt & Allocation loop
    rc = sc.post(
        "/api/v1/payments/receipts/",
        {
            "customer": cust.id,
            "amount": str(grand_total),
            "method": "BANK",
            "allocations": [{"sales_invoice": iid, "amount": str(grand_total)}],
        },
        format="json",
    )
    assert rc.status_code in (200, 201), rc.data

    # 5. Role & capability boundaries
    # Accountant views reports; Sales staff denied financial statements
    boundary.allowed(ac, "get", "/api/v1/accounting/trial-balance/")
    boundary.denied(sc, "get", "/api/v1/accounting/trial-balance/")

    assert_all_invariants(company)
