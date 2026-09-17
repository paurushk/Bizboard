"""Persona Journey — Intelligence, Insights & Actionability Validation.

Validates the BizBoard Intelligence Truth Chain (T6):
1. Data -> Metrics -> Insights -> Action -> Outcome:
   - Low stock fast mover: Item below reorder level sold recently triggers alert.
     * User action: replenishes stock -> alert auto-resolves.
   - Customer credit exposure: Customer near credit limit triggers proactive warning.
     * User action: records receipt allocation -> exposure normalizes -> alert resolves.
   - Leakage detection (Sale below purchase cost):
     * Detects operational revenue/margin leakage with exact money impact in paise.
     * Surfaces actionable remediation link (CTA).
2. Invariants:
   - assert_all_invariants(company) holds throughout the journey.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone

from core.invariants import assert_all_invariants
from insights.alerts import build_business_alerts
from insights.attention import build_attention_rows
from inventory.models import MovementType
from inventory.services import InventoryService
from masters.models import Customer, Product
from payments.services import PaymentService
from tests.personas.fixtures import seed_archetype

pytestmark = pytest.mark.django_db


def test_pj_insights_low_stock_fast_mover_alert_and_reorder_action():
    """T6 Intelligence: Low-stock fast-mover insight triggers and clears upon replenishment."""
    ns = seed_archetype("trader")
    company = ns.company
    oc = ns.owner_client
    cust = ns.customers[0]
    today_str = timezone.localdate().isoformat()

    # Create a fast-moving product with reorder_level=10
    product = Product.objects.create(
        company=company,
        name="Chai Special Leaf 500g",
        sku="CHAI-500",
        hsn_code="090240",
        gst_rate=Decimal("5.00"),
        purchase_price=Decimal("150.00"),
        selling_price=Decimal("200.00"),
        reorder_level=Decimal("10.000"),
        track_inventory=True,
    )

    # Inward initial stock: 12 units
    InventoryService.post_movement(
        company=company,
        product=product,
        movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("12.000"),
        unit_cost=Decimal("150.00"),
        user=ns.owner,
    )

    # 1. Before sale: on_hand=12 > reorder_level=10 -> NO low stock alert
    alerts_before = build_business_alerts(company)
    assert not any(a["code"] == "LOW_STOCK_FAST_MOVER" and a.get("document_id") == product.id for a in alerts_before)

    # 2. Customer buys 5 units -> on_hand becomes 7 (< 10) AND sold within last 14 days
    inv_resp = oc.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust.id,
            "invoice_type": "GST",
            "invoice_date": today_str,
            "items": [
                {"product": product.id, "quantity": "5.000", "unit_price": "200.00", "gst_rate": "5.00"}
            ],
        },
        format="json",
    )
    assert inv_resp.status_code == 201
    comp = oc.post(f"/api/v1/sales/invoices/{inv_resp.data['id']}/complete/")
    assert comp.status_code == 200

    # 3. Intelligence layer evaluates: LOW_STOCK_FAST_MOVER must be raised
    alerts_after = build_business_alerts(company)
    low_stock_alerts = [a for a in alerts_after if a["code"] == "LOW_STOCK_FAST_MOVER" and a.get("document_id") == product.id]
    assert len(low_stock_alerts) == 1, "System must generate low stock alert for fast mover"
    alert = low_stock_alerts[0]
    assert alert["severity"] == "warning"
    assert "below reorder" in alert["message"]
    assert alert["cta_path"] == "/inventory/low-stock"

    # 4. User Action: Business Owner replenishes stock by inwarding 25 units
    InventoryService.post_movement(
        company=company,
        product=product,
        movement_type=MovementType.PURCHASE,
        quantity=Decimal("25.000"),
        unit_cost=Decimal("150.00"),
        user=ns.owner,
    )

    # 5. Outcome: on_hand becomes 32 (> 10) -> Alert automatically clears!
    alerts_resolved = build_business_alerts(company)
    assert not any(a["code"] == "LOW_STOCK_FAST_MOVER" and a.get("document_id") == product.id for a in alerts_resolved)

    assert_all_invariants(company)


def test_pj_insights_customer_credit_limit_near_alert_and_action():
    """T6 Intelligence: Customer credit limit near alert triggers and resolves upon receipt."""
    ns = seed_archetype("trader")
    company = ns.company
    oc = ns.owner_client
    non_batch = [prod for prod in ns.products if not prod.track_batch]
    p = non_batch[0]
    today = timezone.localdate()
    today_str = today.isoformat()

    # Inward stock
    InventoryService.post_movement(
        company=company,
        product=p,
        movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("100.000"),
        unit_cost=Decimal("60.00"),
        user=ns.owner,
    )

    # Create customer with credit_limit = 10,000
    cust = Customer.objects.create(
        company=company,
        name="Shree Ganesh Enterprises",
        state="Karnataka",
        credit_limit=Decimal("10000.00"),
        status=Customer.Status.ACTIVE,
    )

    # 1. Invoice of 72 units at 100 + 18% GST = 7200 + 1296 = 8496.00 (exposure 84.96% >= 80% threshold)
    inv_resp = oc.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust.id,
            "invoice_type": "GST",
            "invoice_date": today_str,
            "items": [
                {"product": p.id, "quantity": "72.000", "unit_price": "100.00", "gst_rate": "18.00"}
            ],
        },
        format="json",
    )
    assert inv_resp.status_code == 201
    comp = oc.post(f"/api/v1/sales/invoices/{inv_resp.data['id']}/complete/")
    assert comp.status_code == 200

    # 2. Alert Engine evaluates: CREDIT_LIMIT_NEAR must trigger
    alerts = build_business_alerts(company)
    credit_alerts = [a for a in alerts if a["code"] == "CREDIT_LIMIT_NEAR" and a.get("document_id") == cust.id]
    assert len(credit_alerts) == 1, "Credit limit exposure warning must be generated"
    assert "near credit limit" in credit_alerts[0]["message"]
    assert credit_alerts[0]["cta_path"] == "/sales/customers"

    # 3. User Action: Business records customer payment receipt of Rs. 5,000
    receipt = PaymentService.create_receipt(
        company=company,
        customer=cust,
        amount=Decimal("5000.00"),
        mode="CASH",
        receipt_date=today,
        user=ns.owner,
    )

    # 4. Outcome: Outstanding drops to Rs. 3,496 (34.96% < 80%) -> Alert clears!
    alerts_after_pay = build_business_alerts(company)
    assert not any(a["code"] == "CREDIT_LIMIT_NEAR" and a.get("document_id") == cust.id for a in alerts_after_pay)

    assert_all_invariants(company)


def test_pj_insights_leakage_detector_sale_below_cost():
    """T6 Intelligence: Attention Center flags sale below purchase cost with paise impact."""
    ns = seed_archetype("trader")
    company = ns.company
    oc = ns.owner_client
    cust = ns.customers[0]
    today_str = timezone.localdate().isoformat()

    # Create product with purchase_price = 100.00
    product = Product.objects.create(
        company=company,
        name="Premium Basmati Rice 1kg",
        sku="RICE-1KG",
        hsn_code="100630",
        gst_rate=Decimal("0.00"),
        purchase_price=Decimal("100.00"),
        selling_price=Decimal("120.00"),
        track_inventory=True,
    )

    # Inward stock
    InventoryService.post_movement(
        company=company,
        product=product,
        movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("50.000"),
        unit_cost=Decimal("100.00"),
        user=ns.owner,
    )

    # Cashier makes a pricing error: sells 10 units at Rs. 80 (Loss of Rs. 20/unit!)
    inv_resp = oc.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust.id,
            "invoice_type": "GST",
            "invoice_date": today_str,
            "items": [
                {"product": product.id, "quantity": "10.000", "unit_price": "80.00", "gst_rate": "0.00"}
            ],
        },
        format="json",
    )
    assert inv_resp.status_code == 201
    comp = oc.post(f"/api/v1/sales/invoices/{inv_resp.data['id']}/complete/")
    assert comp.status_code == 200

    # Attention Center detects revenue leakage
    from django.core.cache import cache
    cache.clear()
    attention_rows = build_attention_rows(company)
    below_cost_items = [r for r in attention_rows if r.get("code") == "SALE_BELOW_COST"]
    assert len(below_cost_items) == 1, "Sale below cost must be flagged as revenue leakage"
    leak = below_cost_items[0]
    assert leak["severity"] == "critical"
    # Money impact: 10 units * Rs. 20 loss = Rs. 200 = 20,000 paise
    assert leak["money_impact_paise"] == 20000
    assert "sold below cost" in leak["title"].lower()
    assert leak["action_href"] == "/inventory/products"

    assert_all_invariants(company)
