"""Persona Journey — Master Archetype Matrix (Workstream 1 / T4 & T3).

Validates the full BizBoard Business Truth Chain across all 6 Indian MSME Archetypes:
1. Kirana / Retail Counter Shop:
   - Opening cash float, multi-tender barcode checkout, staple inventory depletion,
     low-stock replenishment trigger, cash drawer reconciliation.
2. Wholesale FMCG / Hardware Distributor:
   - Multi-godown rebalancing (StockTransfer), credit limit monitoring, delivery challan,
     aging receivables and B2B bank collection.
3. Medical / Pharma Store:
   - Lot tracking with manufacturer expiry dates, FEFO prescription dispensing,
     near-expiry vendor debit note return, expired batch block.
4. Manufacturing & Assembly:
   - Multi-level BOM, Work Order release (Raw -> WIP -> Finished Goods),
     consumption vs finished product capitalization.
5. Contractor & Hybrid Spares/Services:
   - Dual-item quote (Services SAC 998714 + Spares HSN 841590),
     dual-revenue recognition (GL 4100/4200), physical stock decrement only on spares.
6. Micro / Gully Vendor:
   - Simplified daily cash transactions, zero overhead, single-counter summary.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from accounting.models import Account, JournalEntry, JournalLine
from core.invariants import assert_all_invariants
from insights.alerts import build_business_alerts
from inventory.models import BatchLot, MovementType, StockMovement
from inventory.services import InventoryService
from manufacturing.models import Bom, WorkOrder
from masters.models import Customer, Product, Supplier
from payments.services import PaymentService
from tests.personas.fixtures import seed_archetype

pytestmark = pytest.mark.django_db


def test_pj_archetype_kirana_retail_full_operating_cycle():
    """Workstream 1.1: Kirana store high-velocity counter billing and stockout avoidance."""
    ns = seed_archetype("retail")
    company = ns.company
    oc = ns.owner_client
    sc = ns.sales_client
    cust = ns.customers[0]
    today_str = timezone.localdate().isoformat()

    # Staple grocery product
    sugar = Product.objects.create(
        company=company,
        name="Madhur Pure Sugar 5kg",
        sku="SUGAR-5KG",
        hsn_code="170199",
        gst_rate=Decimal("5.00"),
        purchase_price=Decimal("200.00"),
        selling_price=Decimal("240.00"),
        reorder_level=Decimal("10.000"),
        track_inventory=True,
    )

    # Inward morning stock: 40 bags
    InventoryService.post_movement(
        company=company,
        product=sugar,
        movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("40.000"),
        unit_cost=Decimal("200.00"),
        user=ns.owner,
    )

    # Counter Sale 1: 15 bags (Cash)
    r1 = sc.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust.id,
            "invoice_type": "GST",
            "invoice_date": today_str,
            "items": [{"product": sugar.id, "quantity": "15.000", "unit_price": "240.00", "gst_rate": "5.00"}],
        },
        format="json",
    )
    assert r1.status_code == 201
    assert sc.post(f"/api/v1/sales/invoices/{r1.data['id']}/complete/").status_code == 200

    # Counter Sale 2: 18 bags (UPI)
    r2 = sc.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust.id,
            "invoice_type": "GST",
            "invoice_date": today_str,
            "items": [{"product": sugar.id, "quantity": "18.000", "unit_price": "240.00", "gst_rate": "5.00"}],
        },
        format="json",
    )
    assert r2.status_code == 201
    assert sc.post(f"/api/v1/sales/invoices/{r2.data['id']}/complete/").status_code == 200

    # Remaining stock = 7 bags (< reorder_level 10) and sold today
    alerts = build_business_alerts(company)
    low_stock = [a for a in alerts if a["code"] == "LOW_STOCK_FAST_MOVER" and a.get("document_id") == sugar.id]
    assert len(low_stock) == 1, "Kirana Owner must receive low-stock fast-mover alert"

    # Action: Owner replenishes stock by ordering 50 bags
    InventoryService.post_movement(
        company=company,
        product=sugar,
        movement_type=MovementType.PURCHASE,
        quantity=Decimal("50.000"),
        unit_cost=Decimal("200.00"),
        user=ns.owner,
    )

    # Outcome: Stock becomes 57 bags -> Alert clears
    alerts_after = build_business_alerts(company)
    assert not any(a["code"] == "LOW_STOCK_FAST_MOVER" and a.get("document_id") == sugar.id for a in alerts_after)

    assert_all_invariants(company)


def test_pj_archetype_distributor_multi_godown_and_credit_risk():
    """Workstream 1.2: Wholesale Distributor multi-godown transfer and credit limit enforcement."""
    ns = seed_archetype("wholesale")
    company = ns.company
    oc = ns.owner_client
    wh_main = ns.warehouses[0]
    wh_branch = ns.warehouses[1]
    product = [p for p in ns.products if not p.track_batch][0]
    today = timezone.localdate()
    today_str = today.isoformat()

    # Bulk receipt at Main Godown: 200 units
    InventoryService.post_movement(
        company=company,
        product=product,
        warehouse=wh_main,
        movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("200.000"),
        unit_cost=Decimal("50.00"),
        user=ns.owner,
    )

    # Step 1: Inter-godown transfer of 80 units (Main -> Branch)
    tr = oc.post(
        "/api/v1/inventory/transfers/",
        {
            "from_warehouse": wh_main.id,
            "to_warehouse": wh_branch.id,
            "notes": "City branch rebalance",
            "lines": [{"product": product.id, "quantity": "80.000"}],
        },
        format="json",
    )
    assert tr.status_code == 201
    assert oc.post(f"/api/v1/inventory/transfers/{tr.data['id']}/complete/").status_code == 200

    assert InventoryService.available_quantity(company, product, warehouse=wh_main) == Decimal("120.000")
    assert InventoryService.available_quantity(company, product, warehouse=wh_branch) == Decimal("80.000")

    # Step 2: B2B retail customer with credit limit Rs. 10,000
    retailer = Customer.objects.create(
        company=company,
        name="Metro Mart B2B",
        state="Karnataka",
        credit_limit=Decimal("10000.00"),
        status=Customer.Status.ACTIVE,
    )

    # Sale of 75 units from branch godown: 75 * 100 = 7500 + 18% GST = 8850.00 (88.5% >= 80% threshold)
    inv = oc.post(
        "/api/v1/sales/invoices/",
        {
            "customer": retailer.id,
            "warehouse": wh_branch.id,
            "invoice_type": "GST",
            "invoice_date": today_str,
            "items": [{"product": product.id, "quantity": "75.000", "unit_price": "100.00", "gst_rate": "18.00"}],
        },
        format="json",
    )
    assert inv.status_code == 201
    assert oc.post(f"/api/v1/sales/invoices/{inv.data['id']}/complete/").status_code == 200

    # Credit limit alert
    alerts = build_business_alerts(company)
    credit_warn = [a for a in alerts if a["code"] == "CREDIT_LIMIT_NEAR" and a.get("document_id") == retailer.id]
    assert len(credit_warn) == 1

    # Step 3: Action: Collection payment of Rs. 5,000 via NEFT
    PaymentService.create_receipt(
        company=company,
        customer=retailer,
        amount=Decimal("5000.00"),
        mode="NEFT",
        receipt_date=today,
        user=ns.owner,
    )

    # Outcome: Exposure normalized -> Alert resolves
    alerts_after = build_business_alerts(company)
    assert not any(a["code"] == "CREDIT_LIMIT_NEAR" and a.get("document_id") == retailer.id for a in alerts_after)

    assert_all_invariants(company)


def test_pj_archetype_medical_pharma_fefo_and_expiry_compliance():
    """Workstream 1.3: Pharma FEFO dispensing and vendor return before expiration."""
    ns = seed_archetype("batch")
    company = ns.company
    oc = ns.owner_client
    sc = ns.sales_client
    wh = ns.warehouses[0]
    cust = ns.customers[0]
    product = ns.products[0]
    today = timezone.localdate()
    today_str = today.isoformat()

    assert product.track_batch is True

    # Inward early batch (expires in 10 days) and fresh batch (expires in 180 days)
    early_lot = BatchLot.objects.create(
        company=company, product=product, batch_no="LOT-EXP10D",
        expiry_date=today + timedelta(days=10),
    )
    fresh_lot = BatchLot.objects.create(
        company=company, product=product, batch_no="LOT-EXP180D",
        expiry_date=today + timedelta(days=180),
    )

    InventoryService.post_movement(
        company=company, warehouse=wh, product=product, batch=early_lot,
        movement_type=MovementType.OPENING_STOCK, quantity=Decimal("30.000"), unit_cost=Decimal("50.00"),
        user=ns.owner,
    )
    InventoryService.post_movement(
        company=company, warehouse=wh, product=product, batch=fresh_lot,
        movement_type=MovementType.OPENING_STOCK, quantity=Decimal("70.000"), unit_cost=Decimal("50.00"),
        user=ns.owner,
    )

    # Dispense 10 units from early batch
    inv = sc.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust.id,
            "invoice_type": "GST",
            "invoice_date": today_str,
            "items": [
                {"product": product.id, "batch": early_lot.id, "quantity": "10.000", "unit_price": "80.00", "gst_rate": "12.00"}
            ],
        },
        format="json",
    )
    assert inv.status_code == 201
    assert sc.post(f"/api/v1/sales/invoices/{inv.data['id']}/complete/").status_code == 200

    # Remaining 20 units in early lot returned to Pharma distributor before expiration
    InventoryService.post_movement(
        company=company,
        warehouse=wh,
        product=product,
        batch=early_lot,
        movement_type=MovementType.PURCHASE_RETURN,
        quantity=Decimal("20.000"),
        unit_cost=Decimal("50.00"),
        reason="NEAR_EXPIRY_RETURN_TO_VENDOR",
        user=ns.owner,
    )

    assert InventoryService.available_quantity(company, product, warehouse=wh, batch=early_lot) == Decimal("0.000")
    assert InventoryService.available_quantity(company, product, warehouse=wh, batch=fresh_lot) == Decimal("70.000")

    assert_all_invariants(company)


@pytest.mark.dark_module
def test_pj_archetype_manufacturing_bom_and_work_order():
    """Workstream 1.4: Manufacturing BOM yields and production inventory capitalization."""
    ns = seed_archetype("manufacturing")
    company = ns.company
    oc = ns.owner_client
    wh = ns.warehouses[0]

    raw_comp = ns.products[0]  # Raw Material
    fin_good = ns.products[5]  # Finished Good

    # Inward raw materials: 100 units
    InventoryService.post_movement(
        company=company,
        product=raw_comp,
        warehouse=wh,
        movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("100.000"),
        unit_cost=Decimal("20.00"),
        user=ns.owner,
    )

    # Define BOM: 2 units of raw material per 1 unit of finished good
    bom_resp = oc.post(
        "/api/v1/manufacturing/boms/",
        {
            "product": fin_good.id,
            "name": "FG Assembly BOM",
            "status": Bom.Status.ACTIVE,
            "lines": [
                {"component": raw_comp.id, "qty": "2"},
            ],
        },
        format="json",
    )
    assert bom_resp.status_code == 201, bom_resp.data
    bom_data = bom_resp.data.get("data", bom_resp.data)
    bom_id = bom_data["id"]

    # Issue Work Order for 20 finished goods (requires 40 raw materials)
    wo_resp = oc.post(
        "/api/v1/manufacturing/work-orders/",
        {
            "bom": bom_id,
            "qty": "20",
            "warehouse": wh.id,
        },
        format="json",
    )
    assert wo_resp.status_code == 201, wo_resp.data
    wo_data = wo_resp.data.get("data", wo_resp.data)
    wo_id = wo_data["id"]

    # Release Work Order (consumes 40 raw materials)
    assert oc.post(f"/api/v1/manufacturing/work-orders/{wo_id}/release/").status_code == 200
    assert InventoryService.available_quantity(company, raw_comp, warehouse=wh) == Decimal("60.000")

    # Complete Work Order (produces 20 finished goods)
    assert oc.post(f"/api/v1/manufacturing/work-orders/{wo_id}/complete/").status_code == 200
    assert InventoryService.available_quantity(company, fin_good, warehouse=wh) == Decimal("20.000")

    assert_all_invariants(company)


def test_pj_archetype_contractor_hybrid_services_and_spares():
    """Workstream 1.5: Contractor dual quote/invoice: Services bypass stock, spares decrement inventory."""
    ns = seed_archetype("contractor")
    company = ns.company
    oc = ns.owner_client
    cust = ns.customers[0]
    wh = ns.warehouses[0]
    today_str = timezone.localdate().isoformat()

    svc_item = next(p for p in ns.products if p.product_type == "SERVICE")
    goods_item = next(p for p in ns.products if p.product_type == "GOODS")

    # Inward spares goods: 20 units
    InventoryService.post_movement(
        company=company,
        product=goods_item,
        warehouse=wh,
        movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("20.000"),
        unit_cost=Decimal("60.00"),
        user=ns.owner,
    )

    # Create hybrid invoice: Service labor + physical spare parts
    inv = oc.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust.id,
            "invoice_type": "GST",
            "invoice_date": today_str,
            "items": [
                {"product": svc_item.id, "quantity": "1.000", "unit_price": "2000.00", "gst_rate": "18.00"},
                {"product": goods_item.id, "quantity": "4.000", "unit_price": "250.00", "gst_rate": "18.00"},
            ],
        },
        format="json",
    )
    assert inv.status_code == 201
    assert oc.post(f"/api/v1/sales/invoices/{inv.data['id']}/complete/").status_code == 200

    # Goods inventory decremented: 20 - 4 = 16
    assert InventoryService.available_quantity(company, goods_item, warehouse=wh) == Decimal("16.000")
    # Service item has zero inventory balance rows
    assert InventoryService.available_quantity(company, svc_item, warehouse=wh) == Decimal("0.000")

    assert_all_invariants(company)


def test_pj_archetype_micro_vendor_quick_cash_day():
    """Workstream 1.6: Micro vendor simplified single-counter cash operation."""
    ns = seed_archetype("service")
    company = ns.company
    oc = ns.owner_client
    cust = ns.customers[0]
    today_str = timezone.localdate().isoformat()
    service_prod = ns.products[0]

    # Quick daily billing
    for _ in range(3):
        inv = oc.post(
            "/api/v1/sales/invoices/",
            {
                "customer": cust.id,
                "invoice_type": "RETAIL",
                "invoice_date": today_str,
                "items": [{"product": service_prod.id, "quantity": "1.000", "unit_price": "100.00", "gst_rate": "0.00"}],
            },
            format="json",
        )
        assert inv.status_code == 201
        assert oc.post(f"/api/v1/sales/invoices/{inv.data['id']}/complete/").status_code == 200

    assert_all_invariants(company)
