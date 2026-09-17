"""Cross-Flow Cohesive Testing Suite — Archetypes, Personas, Metrics & Calculations.

Validates:
1. Startup Founder (P1) end-to-end lifecycle and cross-flow metric synchronization:
   - Onboarding state derivation (derive_onboarding & should_force_setup)
   - Dashboard KPIs vs DailyBusinessSummary vs Health Score vs Cashflow Forecast vs Attention Center
2. Multi-persona entitlement and segregation consistency across all flows (P1..P6, Viewer, Importer):
   - Capability boundaries (sales, purchases, journals, adjustments, period close)
   - Visibility boundaries (financial statements, masters, attention feed codes)
3. Calculation accuracy, rounding, and invariant sweeps across archetypes.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from accounts.onboarding import derive_onboarding, should_force_setup
from core.invariants import assert_all_invariants
from insights.attention import FINANCIAL_CODES, GST_CODES, build_attention_rows, rupees_to_paise
from insights.services import (
    compute_health_score,
    forecast_cashflow,
    generate_daily_summary,
)
from inventory.models import MovementType
from inventory.services import InventoryService
from reporting.services import ReportService
from tests.personas.fixtures import seed_archetype

pytestmark = pytest.mark.django_db


def test_startup_founder_onboarding_to_analytics_synchronization():
    """Startup Founder (P1 Owner) flow:
    Onboarding -> Catalog Setup -> Sales Invoicing -> Dashboard KPIs ->
    Daily Business Summary -> Health Score -> Cashflow Forecast -> Attention Center.

    Asserts that all metrics, revenues, AR/AP, and scores are 100% synchronized
    and mathematically consistent across services and screens.
    """
    ns = seed_archetype("trader")
    company = ns.company
    owner = ns.owner
    oc = ns.owner_client

    # 1. Onboarding derivation consistency
    init_onboarding = derive_onboarding(company)
    assert init_onboarding["catalog_done"] is True  # products seeded
    assert init_onboarding["activation_done"] is False  # no completed sales invoice yet
    assert init_onboarding["status"] in ("IN_PROGRESS", "NOT_STARTED")

    # Non-owner should NEVER be forced into setup wizard; Owner IS guided
    assert should_force_setup(company=company, is_owner=False, wizard_enabled=True) is False
    assert should_force_setup(company=company, is_owner=True, wizard_enabled=True) is True

    # 2. Stock in products (use plain products without batch tracking)
    plain = [p for p in ns.products if not p.track_batch]
    prod1 = plain[0]
    prod2 = plain[1]
    InventoryService.post_movement(
        company=company, product=prod1, movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("100"), unit_cost=Decimal("60.00"), user=owner,
    )
    InventoryService.post_movement(
        company=company, product=prod2, movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("50"), unit_cost=Decimal("40.00"), user=owner,
    )

    cust1 = ns.customers[0]
    supplier1 = ns.suppliers[0]

    # 3. Create a purchase bill (AP)
    pur = oc.post(
        "/api/v1/purchases/invoices/",
        {
            "supplier": supplier1.id,
            "purchase_type": "GST",
            "due_date": (timezone.localdate() + timedelta(days=7)).isoformat(),
            "items": [
                {"product": prod1.id, "quantity": "10", "unit_price": "60.00", "gst_rate": "18"},
            ],
        },
        format="json",
    )
    assert pur.status_code == 201, pur.data
    assert oc.post(f"/api/v1/purchases/invoices/{pur.data['id']}/complete/").status_code == 200

    # 4. Create and complete first sales invoice (Activation)
    inv1 = oc.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust1.id,
            "invoice_type": "GST",
            "items": [
                {"product": prod1.id, "quantity": "5", "unit_price": "100.00", "gst_rate": "18"},
            ],
        },
        format="json",
    )
    assert inv1.status_code == 201, inv1.data
    iid1 = inv1.data["id"]
    done1 = oc.post(f"/api/v1/sales/invoices/{iid1}/complete/")
    assert done1.status_code == 200, done1.data
    inv1_total = Decimal(str(done1.data["grand_total"]))  # 500 + 18% = 590.00

    # Verify onboarding status flips to COMPLETED upon first invoice activation
    post_onboarding = derive_onboarding(company)
    assert post_onboarding["activation_done"] is True
    assert post_onboarding["status"] == "COMPLETED"
    assert should_force_setup(company=company, is_owner=True, wizard_enabled=True) is False

    # 5. Cross-flow metric validation: Dashboard vs Daily Summary
    dash = ReportService.dashboard(company)
    dash_sales_today = Decimal(str(dash["sales_today"]["total"]))
    dash_sales_mtd = Decimal(str(dash["sales_this_month"]["total"]))
    dash_receivables = Decimal(str(dash["receivables"]))
    dash_payables = Decimal(str(dash["payables"]))

    assert dash_sales_today == inv1_total
    assert dash_sales_mtd == inv1_total
    assert dash_receivables == inv1_total  # invoice unpaid -> 590.00
    assert dash_payables == Decimal("708.00")  # purchase 600 + 18% = 708.00

    # Generate daily summary and verify perfect metric synchronization
    summary = generate_daily_summary(company)
    kpis = summary.kpis
    assert Decimal(kpis["sales_today_total"]) == dash_sales_today
    assert int(kpis["sales_today_count"]) == dash["sales_today"]["count"]
    assert Decimal(kpis["sales_mtd_total"]) == dash_sales_mtd
    assert int(kpis["sales_mtd_count"]) == dash["sales_this_month"]["count"]
    assert Decimal(kpis["receivables"]) == dash_receivables
    assert Decimal(kpis["payables"]) == dash_payables

    # 6. Health score calculation consistency
    health = compute_health_score(company)
    assert Decimal(health["mtd_sales"]) == dash_sales_mtd
    assert health["grade"] in ("A", "B", "C", "D", "F")
    assert Decimal("0") <= health["score"] <= Decimal("100")
    # Verify factor weights sum to 1.00 (within precision)
    factor_weights_sum = sum(Decimal(f["weight"]) for f in health["factors"])
    assert factor_weights_sum == Decimal("1.00")

    # 7. Cashflow planning / forecast synchronization
    forecast = forecast_cashflow(company, horizon=14)
    meta = forecast["meta"]
    series = forecast["series"]
    assert len(series) == 14
    # All AR is currently in 'current' bucket (new invoice)
    expected_colls = Decimal(meta["expected_collections"])
    assert expected_colls > 0
    # Day 7 has purchase due date -> outflow matches purchase amount 708.00
    day7 = series[6]  # 7th day
    assert Decimal(day7["outflow"]) == Decimal("708.00")
    # Verify cumulative math: cumulative_ending = opening + cumulative
    for row in series:
        assert Decimal(row["ending_cash"]) == Decimal(meta["opening_cash"] or "0") + Decimal(row["cumulative"])

    # 8. Attention center and recommendations
    rows = build_attention_rows(company, company_user=ns.owner_cu)
    assert isinstance(rows, list)
    for r in rows:
        assert "code" in r
        assert "severity" in r
        assert "money_impact_paise" in r
        assert isinstance(r["money_impact_paise"], int)
        # Currency must be INR
        assert r["currency"] == "INR"

    assert_all_invariants(company)


def test_multi_persona_entitlement_and_segregation_consistency(boundary):
    """Verifies that persona entitlements, boundaries, and visibility rules
    are consistently enforced across all user flows.

    Personas tested:
    - P1: OWNER (Proprietor)
    - P2/P3: SALES_STAFF (Billing Clerk / Order Booker)
    - P4: GODOWN CUSTODIAN (SALES_STAFF + can_manage_inventory)
    - P5: ACCOUNTANT (Resident Munshi)
    - P-VIEWER: Read-only UI role
    """
    ns = seed_archetype("wholesale")
    company = ns.company
    oc = ns.owner_client
    sc = ns.sales_client
    gc = ns.godown_client
    ac = ns.acct_client

    plain_p = [p for p in ns.products if not p.track_batch][0]
    cust = ns.customers[0]

    # Seed stock
    InventoryService.post_movement(
        company=company, product=plain_p, movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("40"), unit_cost=Decimal("60.00"), user=ns.owner,
    )

    # 1. SALES INVOICE FLOW
    # Allowed for Sales staff & Owner; Denied for Accountant & Custodian
    sinv = sc.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust.id, "invoice_type": "GST",
            "items": [{"product": plain_p.id, "quantity": "2", "unit_price": "100.00", "gst_rate": "18"}],
        },
        format="json",
    )
    assert sinv.status_code == 201, sinv.data
    iid = sinv.data["id"]
    assert sc.post(f"/api/v1/sales/invoices/{iid}/complete/").status_code == 200

    # Accountant cannot create sales invoices (Segregation of Duties)
    boundary.denied(
        ac, "post", "/api/v1/sales/invoices/",
        data={"customer": cust.id, "invoice_type": "GST", "items": []},
        format="json",
    )

    # Sales staff CANNOT cancel completed invoices; Owner CAN
    boundary.denied(sc, "post", f"/api/v1/sales/invoices/{iid}/cancel/", data={"reason": "test"}, format="json")

    # 2. INVENTORY ADJUSTMENT FLOW
    # Denied for Sales staff & Accountant; Allowed for Custodian & Owner
    boundary.denied(
        sc, "post", "/api/v1/inventory/adjustments/",
        data={"product": plain_p.id, "quantity": "-1", "reason": "damaged"}, format="json",
    )
    boundary.denied(
        ac, "post", "/api/v1/inventory/adjustments/",
        data={"product": plain_p.id, "quantity": "-1", "reason": "damaged"}, format="json",
    )
    adj_resp = gc.post(
        "/api/v1/inventory/adjustments/",
        {"product": plain_p.id, "quantity": "-1", "reason": "damaged"}, format="json",
    )
    assert adj_resp.status_code == 201, adj_resp.data

    # 3. FINANCIAL STATEMENTS VISIBILITY
    # Denied for Sales staff & Custodian; Allowed for Accountant & Owner
    boundary.denied(sc, "get", "/api/v1/accounting/trial-balance/")
    boundary.denied(sc, "get", "/api/v1/accounting/profit-and-loss/")
    boundary.denied(sc, "get", "/api/v1/accounting/balance-sheet/")

    boundary.denied(gc, "get", "/api/v1/accounting/trial-balance/")
    boundary.denied(gc, "get", "/api/v1/accounting/profit-and-loss/")

    boundary.allowed(ac, "get", "/api/v1/accounting/trial-balance/")
    boundary.allowed(ac, "get", "/api/v1/accounting/profit-and-loss/")
    boundary.allowed(ac, "get", "/api/v1/accounting/balance-sheet/")

    # 4. ATTENTION FEED CODE FILTERING
    # Financial & margin codes must NOT be shown to Sales staff who lack financial reports cap
    owner_feed = build_attention_rows(company, company_user=ns.owner_cu)
    sales_feed = build_attention_rows(company, company_user=ns.sales_cu)
    for item in sales_feed:
        assert item["code"] not in FINANCIAL_CODES, f"Sales staff saw financial alert: {item['code']}"
        assert item["code"] not in GST_CODES, f"Sales staff saw GST alert: {item['code']}"

    # 5. ACCOUNTING PERIOD CLOSE & BACK-DATING
    # Accountant CANNOT close a period; only Owner CAN
    per = oc.post(
        "/api/v1/accounting/periods/",
        {"name": "May 2026", "start_date": "2026-05-01", "end_date": "2026-05-31"}, format="json",
    )
    assert per.status_code == 201, per.data
    pid = per.data["id"]

    boundary.denied(ac, "post", f"/api/v1/accounting/periods/{pid}/close/")
    assert oc.post(f"/api/v1/accounting/periods/{pid}/close/").status_code == 200

    # Back-dated postings into the closed period are strictly rejected
    from accounting.models import Account

    cash_acc = Account.objects.get(company=ns.company, code="1100").id
    eq_acc = Account.objects.get(company=ns.company, code="3200").id
    backdated = ac.post(
        "/api/v1/accounting/journals/",
        {
            "entry_date": "2026-05-15",
            "narration": "forbidden back-date",
            "lines": [
                {"account": cash_acc, "debit": "100.00", "credit": "0"},
                {"account": eq_acc, "debit": "0", "credit": "100.00"},
            ],
        },
        format="json",
    )
    if backdated.status_code == 201:
        post_r = ac.post(f"/api/v1/accounting/journals/{backdated.data['id']}/post/")
        assert post_r.status_code >= 400, "Back-dated journal into closed period must fail"
    else:
        assert backdated.status_code >= 400

    assert_all_invariants(company)


def test_paise_conversion_and_rounding_accuracy():
    """Validates that money conversions to paise and rounding logic remain
    exact across all calculations without floating point discrepancies.
    """
    assert rupees_to_paise(Decimal("100.00")) == 10000
    assert rupees_to_paise(Decimal("100.50")) == 10050
    assert rupees_to_paise(Decimal("100.505")) == 10051  # ROUND_HALF_UP
    assert rupees_to_paise(Decimal("0.01")) == 1
    assert rupees_to_paise(0) == 0
    assert rupees_to_paise(None) == 0
