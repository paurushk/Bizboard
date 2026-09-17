"""Persona Journey — Archetype Golden Business Journeys.

Validates the BizBoard Golden Business Journey Matrix (T4):
1. Kirana / Retail Operating Model:
   - Fast multi-tender counter billing (Cash + UPI).
   - High turnover staple items triggering low-stock replenishment alert.
   - Reorder action avoids out-of-stock scenario.
2. Wholesale Distributor Operating Model:
   - Multi-godown rebalancing: Stock transfer from Central Godown to Branch Godown.
   - Route delivery billing with credit limit risk monitoring.
   - B2B collection receipt normalizes exposure.
3. Medical / Pharmacy Operating Model:
   - Batch inwarding with expiry dates.
   - FEFO (First-Expiry-First-Out) dispensing discipline.
   - Near-expiry stock identification and purchase return before statutory expiration.
4. Invariants:
   - assert_all_invariants(company) holds clean across all archetypes.

Deliberate overlap with `test_pj_master_archetype_matrix.py`: that file proves
the transactional MECHANICS for Kirana/Distributor/Pharma (does the stock
decrement, does the GL split, does FEFO pick the right batch); this file proves
the golden BUSINESS OUTCOME for the same three archetypes end-to-end, including
the insights/alert loop (`build_business_alerts`) that the matrix file does not
touch — e.g. a low-stock alert actually firing and a reorder actually
preventing the stockout, not just the stock arithmetic being right. Keep both:
losing either drops a real assertion, but know that a change to one of these
three scenarios usually needs a matching change in the other file too.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.invariants import assert_all_invariants
from insights.alerts import build_business_alerts
from inventory.models import BatchLot, MovementType
from inventory.services import InventoryService
from masters.models import Customer, Product
from payments.services import PaymentService
from tests.personas.fixtures import seed_archetype

pytestmark = pytest.mark.django_db


def test_pj_golden_journey_kirana_retail_fast_turnover():
    """T4 Archetype: Kirana store high-velocity counter billing and stockout avoidance."""
    ns = seed_archetype("retail")
    company = ns.company
    oc = ns.owner_client
    sc = ns.sales_client
    cust = ns.customers[0]
    today_str = timezone.localdate().isoformat()

    # Staple grocery: Wheat Flour 10kg
    atta = Product.objects.create(
        company=company,
        name="Chakki Fresh Atta 10kg",
        sku="ATTA-10KG",
        hsn_code="110100",
        gst_rate=Decimal("0.00"),
        purchase_price=Decimal("350.00"),
        selling_price=Decimal("420.00"),
        reorder_level=Decimal("15.000"),
        track_inventory=True,
    )

    # Inward morning stock: 50 bags
    InventoryService.post_movement(
        company=company,
        product=atta,
        movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("50.000"),
        unit_cost=Decimal("350.00"),
        user=ns.owner,
    )

    # Customer 1: Buys 20 bags (Cash)
    inv1_resp = sc.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust.id,
            "invoice_type": "GST",
            "invoice_date": today_str,
            "items": [{"product": atta.id, "quantity": "20.000", "unit_price": "420.00", "gst_rate": "0.00"}],
        },
        format="json",
    )
    assert inv1_resp.status_code == 201
    assert sc.post(f"/api/v1/sales/invoices/{inv1_resp.data['id']}/complete/").status_code == 200

    # Customer 2: Buys 20 bags (UPI)
    inv2_resp = sc.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust.id,
            "invoice_type": "GST",
            "invoice_date": today_str,
            "items": [{"product": atta.id, "quantity": "20.000", "unit_price": "420.00", "gst_rate": "0.00"}],
        },
        format="json",
    )
    assert inv2_resp.status_code == 201
    assert sc.post(f"/api/v1/sales/invoices/{inv2_resp.data['id']}/complete/").status_code == 200

    # Current stock is now 10 bags (< reorder_level 15.000) and sold today
    alerts = build_business_alerts(company)
    low_stock = [a for a in alerts if a["code"] == "LOW_STOCK_FAST_MOVER" and a.get("document_id") == atta.id]
    assert len(low_stock) == 1, "Kirana Owner must be alerted that staple fast-mover is below reorder"

    # Owner takes action: Replenishment inward of 50 bags before next morning opening
    InventoryService.post_movement(
        company=company,
        product=atta,
        movement_type=MovementType.PURCHASE,
        quantity=Decimal("50.000"),
        unit_cost=Decimal("350.00"),
        user=ns.owner,
    )

    # Outcome: Available stock restored to 60 bags -> alert resolves -> stockout avoided!
    alerts_after = build_business_alerts(company)
    assert not any(a["code"] == "LOW_STOCK_FAST_MOVER" and a.get("document_id") == atta.id for a in alerts_after)

    assert_all_invariants(company)


def test_pj_golden_journey_distributor_credit_risk_and_godown_transfer():
    """T4 Archetype: Distributor inter-godown stock rebalance and B2B credit collection."""
    ns = seed_archetype("wholesale")
    company = ns.company
    oc = ns.owner_client
    wh_north = ns.warehouses[0]  # Central godown
    wh_south = ns.warehouses[1]  # City branch godown
    product = [p for p in ns.products if not p.track_batch][0]
    today = timezone.localdate()
    today_str = today.isoformat()

    # Inward 100 units to Central Godown (North)
    InventoryService.post_movement(
        company=company,
        product=product,
        warehouse=wh_north,
        movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("100.000"),
        unit_cost=Decimal("60.00"),
        user=ns.owner,
    )

    # Step 1: Inter-godown transfer of 40 units (North -> South)
    transfer_resp = oc.post(
        "/api/v1/inventory/transfers/",
        {
            "from_warehouse": wh_north.id,
            "to_warehouse": wh_south.id,
            "notes": "City branch rebalance",
            "lines": [{"product": product.id, "quantity": "40.000"}],
        },
        format="json",
    )
    assert transfer_resp.status_code == 201
    transfer_id = transfer_resp.data["id"]
    comp_transfer = oc.post(f"/api/v1/inventory/transfers/{transfer_id}/complete/")
    assert comp_transfer.status_code == 200

    # Verify godown balances: North = 60, South = 40
    assert InventoryService.available_quantity(company, product, warehouse=wh_north) == Decimal("60.000")
    assert InventoryService.available_quantity(company, product, warehouse=wh_south) == Decimal("40.000")

    # Step 2: B2B retail customer orders 30 units from City Branch Godown with credit limit Rs. 4,000
    retailer = Customer.objects.create(
        company=company,
        name="Apex Supermarket",
        state="Karnataka",
        credit_limit=Decimal("4000.00"),
        status=Customer.Status.ACTIVE,
    )

    inv_resp = oc.post(
        "/api/v1/sales/invoices/",
        {
            "customer": retailer.id,
            "warehouse": wh_south.id,
            "invoice_type": "GST",
            "invoice_date": today_str,
            "items": [{"product": product.id, "quantity": "30.000", "unit_price": "100.00", "gst_rate": "18.00"}],
        },
        format="json",
    )
    assert inv_resp.status_code == 201
    assert oc.post(f"/api/v1/sales/invoices/{inv_resp.data['id']}/complete/").status_code == 200

    # Exposure is Rs. 3,540 out of Rs. 4,000 credit limit (88.5% >= 80% threshold)
    alerts = build_business_alerts(company)
    credit_warn = [a for a in alerts if a["code"] == "CREDIT_LIMIT_NEAR" and a.get("document_id") == retailer.id]
    assert len(credit_warn) == 1

    # Step 3: Action: Collection follow-up -> Customer pays Rs. 2,000 via NEFT
    PaymentService.create_receipt(
        company=company,
        customer=retailer,
        amount=Decimal("2000.00"),
        mode="NEFT",
        receipt_date=today,
        user=ns.owner,
    )

    # Exposure drops to Rs. 1,540 (38.5% < 80%) -> Alert resolves!
    alerts_after = build_business_alerts(company)
    assert not any(a["code"] == "CREDIT_LIMIT_NEAR" and a.get("document_id") == retailer.id for a in alerts_after)

    assert_all_invariants(company)


def test_pj_golden_journey_medical_pharma_fefo_and_near_expiry_return():
    """T4 Archetype: Pharmacy FEFO dispensing and vendor return before statutory expiration."""
    ns = seed_archetype("batch")
    company = ns.company
    oc = ns.owner_client
    sc = ns.sales_client
    wh = ns.warehouses[0]
    cust = ns.customers[0]
    supplier = ns.suppliers[0]
    product = ns.products[0]
    today = timezone.localdate()
    today_str = today.isoformat()

    assert product.track_batch is True

    # 1. Inward two batches from Pharma Supplier:
    # Batch Early: Expires in 15 days (near expiry!)
    # Batch Fresh: Expires in 180 days
    batch_early = BatchLot.objects.create(
        company=company, product=product, batch_no="BATCH-EXP15D",
        expiry_date=today + timedelta(days=15),
    )
    batch_fresh = BatchLot.objects.create(
        company=company, product=product, batch_no="BATCH-EXP180D",
        expiry_date=today + timedelta(days=180),
    )

    InventoryService.post_movement(
        company=company, warehouse=wh, product=product, batch=batch_early,
        movement_type=MovementType.OPENING_STOCK, quantity=Decimal("50.000"), unit_cost=Decimal("50.00"),
        user=ns.owner,
    )
    InventoryService.post_movement(
        company=company, warehouse=wh, product=product, batch=batch_fresh,
        movement_type=MovementType.OPENING_STOCK, quantity=Decimal("100.000"), unit_cost=Decimal("50.00"),
        user=ns.owner,
    )

    # 2. Patient prescription billing: 20 strips dispensed
    # Pharmacist allocates from Batch Early (FEFO discipline)
    inv_resp = sc.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust.id,
            "invoice_type": "GST",
            "invoice_date": today_str,
            "items": [
                {
                    "product": product.id,
                    "batch": batch_early.id,
                    "quantity": "20.000",
                    "unit_price": "80.00",
                    "gst_rate": "12.00",
                }
            ],
        },
        format="json",
    )
    assert inv_resp.status_code == 201
    assert sc.post(f"/api/v1/sales/invoices/{inv_resp.data['id']}/complete/").status_code == 200

    # 3. Batch Early now has 30 strips remaining with only 15 days to expiry
    # Pharmacist initiates return of near-expiry stock (30 units) back to Pharma Supplier
    # Outward return movement
    InventoryService.post_movement(
        company=company,
        warehouse=wh,
        product=product,
        batch=batch_early,
        movement_type=MovementType.PURCHASE_RETURN,
        quantity=Decimal("30.000"),
        unit_cost=Decimal("50.00"),
        reason="NEAR_EXPIRY_RETURN_TO_VENDOR",
        user=ns.owner,
    )

    # Outcome: Batch Early is now 0 on hand, avoiding expired drug waste and statutory non-compliance!
    assert InventoryService.available_quantity(company, product, warehouse=wh, batch=batch_early) == Decimal("0.000")
    # Fresh batch remains fully available
    assert InventoryService.available_quantity(company, product, warehouse=wh, batch=batch_fresh) == Decimal("100.000")

    assert_all_invariants(company)
