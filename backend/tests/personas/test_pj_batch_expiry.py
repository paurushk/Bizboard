"""PJ-BATCH-EXPIRY — ARCH-05 Batch & Expiry-Sensitive Stockist Journey.

Validates:
1. Batch inwarding by P4 Godown Custodian with lot numbers and expiry dates.
2. FEFO (First-Expiry-First-Out) picking enforcement on sales invoices.
3. Expiry monitoring & Attention feed EXPIRING_STOCK warnings.
4. Active expiry-block policy (block_expired_stock = True) rejection of expired stock.
5. Role boundaries between Godown Custodian, Sales Staff, and Owner.
6. Clean invariant sweeps across all operations.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.invariants import assert_all_invariants
from insights.attention import build_attention_rows
from inventory.models import BatchLot, MovementType
from inventory.services import InventoryService
from tests.personas.fixtures import seed_archetype

pytestmark = pytest.mark.django_db


def test_pj_batch_expiry_fefo_and_guard_journey(boundary):
    ns = seed_archetype("batch")
    company = ns.company
    oc = ns.owner_client
    sc = ns.sales_client
    gc = ns.godown_client
    product = ns.products[0]
    cust = ns.customers[0]
    wh = ns.warehouses[0]
    today = timezone.localdate()

    assert product.track_batch is True

    # 1. P4 Godown Custodian inwards two distinct batches: EARLY (expiring in 5 days) and LATE (expiring in 30 days)
    early_lot = BatchLot.objects.create(
        company=company, product=product, batch_no="LOT-EARLY",
        expiry_date=today + timedelta(days=5),
    )
    late_lot = BatchLot.objects.create(
        company=company, product=product, batch_no="LOT-LATE",
        expiry_date=today + timedelta(days=30),
    )

    InventoryService.post_movement(
        company=company, warehouse=wh, product=product, batch=early_lot,
        movement_type=MovementType.OPENING_STOCK, quantity=Decimal("10"), unit_cost=Decimal("50.00"),
        user=ns.godown,
    )
    InventoryService.post_movement(
        company=company, warehouse=wh, product=product, batch=late_lot,
        movement_type=MovementType.OPENING_STOCK, quantity=Decimal("20"), unit_cost=Decimal("50.00"),
        user=ns.godown,
    )

    assert InventoryService.available_quantity(company, product, wh, early_lot) == Decimal("10.000")
    assert InventoryService.available_quantity(company, product, wh, late_lot) == Decimal("20.000")
    assert InventoryService.available_quantity(company, product, wh) == Decimal("30.000")

    # 2. Expiry alert detection in Attention Feed
    # Since LOT-EARLY expires in 5 days (<= 30 days horizon), an EXPIRING_STOCK alert must appear
    attention = build_attention_rows(company, company_user=ns.owner_cu)
    expiring_alerts = [r for r in attention if r["code"] == "EXPIRING_STOCK"]
    assert len(expiring_alerts) >= 1
    assert "LOT-EARLY" in expiring_alerts[0]["reason"] or product.name in expiring_alerts[0]["title"]

    # 3. P2/P3 Sales Staff raises invoice without manually specifying batch
    # FEFO picking must consume from LOT-EARLY first
    inv = sc.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust.id,
            "invoice_type": "GST",
            "items": [{"product": product.id, "quantity": "6", "unit_price": "100.00", "gst_rate": "18"}],
        },
        format="json",
    )
    assert inv.status_code == 201, inv.data
    iid = inv.data["id"]

    complete_resp = sc.post(f"/api/v1/sales/invoices/{iid}/complete/")
    assert complete_resp.status_code == 200, complete_resp.data

    # Verify LOT-EARLY decreased by 6 (10 -> 4), LOT-LATE remained untouched (20)
    assert InventoryService.available_quantity(company, product, wh, early_lot) == Decimal("4.000")
    assert InventoryService.available_quantity(company, product, wh, late_lot) == Decimal("20.000")
    assert InventoryService.available_quantity(company, product, wh) == Decimal("24.000")

    # 4. Expired Stock Blocking Policy Guard
    company.block_expired_stock = True
    company.save(update_fields=["block_expired_stock"])

    expired_lot = BatchLot.objects.create(
        company=company, product=product, batch_no="LOT-EXPIRED",
        expiry_date=today - timedelta(days=2),
    )
    InventoryService.post_movement(
        company=company, warehouse=wh, product=product, batch=expired_lot,
        movement_type=MovementType.OPENING_STOCK, quantity=Decimal("5"), unit_cost=Decimal("50.00"),
        user=ns.owner,
    )

    # Attempting to invoice the expired batch must fail under active policy
    inv_expired = oc.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust.id,
            "invoice_type": "GST",
            "items": [
                {
                    "product": product.id, "quantity": "2", "unit_price": "100.00", "gst_rate": "18",
                    "batch": expired_lot.id,
                },
            ],
        },
        format="json",
    )
    if inv_expired.status_code == 201:
        bad_complete = oc.post(f"/api/v1/sales/invoices/{inv_expired.data['id']}/complete/")
        assert bad_complete.status_code >= 400, "Invoicing expired batch must fail under active policy"
    else:
        assert inv_expired.status_code >= 400

    # 5. Role & capability boundaries
    # Sales staff cannot adjust stock; Custodian cannot access P&L
    boundary.denied(sc, "post", "/api/v1/inventory/adjustments/", data={"product": product.id, "quantity": "-1", "reason": "loss"}, format="json")
    boundary.denied(gc, "get", "/api/v1/accounting/profit-and-loss/")

    assert_all_invariants(company)
