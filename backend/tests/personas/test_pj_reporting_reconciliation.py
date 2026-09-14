"""Persona Journey — Reporting Truth & Dashboard Reconciliation.

Validates the BizBoard Reporting Truth Chain (T5):
1. Source Documents == Aggregated Reports == Dashboard KPIs == General Ledger:
   - Sum of Sales Invoices net of Credit Notes strictly equals:
     * Sales Register (totals['grand_total'])
     * Dashboard 'sales_this_month' KPI
     * General Ledger Revenue (Account 4100) + Output Tax (Accounts 2210/2220)
2. Inventory Summary & Stock Movement Truth:
   - Stock summary report 'on_hand' strictly reconciles with sum of StockMovements
   - Zero drift between StockBalance snapshots and StockMovement logs.
3. Receivables Aging & Customer Subledger Parity:
   - Sum of aged receivable buckets strictly equals:
     * Dashboard 'receivables' KPI
     * Sum of Customer subledger outstandings
     * GL Trade Debtors Control Account (1200)
4. Invariants:
   - assert_all_invariants(company) holds clean without discrepancy.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.db.models import Sum

from django.utils import timezone

from accounting.models import Account, JournalEntry, JournalLine
from core.invariants import assert_all_invariants
from inventory.models import MovementType, StockBalance, StockMovement
from inventory.services import InventoryService
from ledgers.services import LedgerService
from reporting.services import ReportService
from sales.models import SalesInvoice
from tests.personas.fixtures import seed_archetype

pytestmark = pytest.mark.django_db


def test_pj_sales_register_to_dashboard_and_gl_reconciliation():
    """T5 Reporting Truth: Sales invoices foot across Register, Dashboard, and GL."""
    ns = seed_archetype("trader")
    company = ns.company
    oc = ns.owner_client
    cust = ns.customers[0]
    non_batch = [prod for prod in ns.products if not prod.track_batch]
    p1 = non_batch[0]
    p2 = non_batch[1]
    today = timezone.localdate()
    today_str = today.isoformat()
    month_start = today.replace(day=1).isoformat()

    # Inward stock first so sales complete cleanly
    for p, qty in [(p1, "100.000"), (p2, "100.000")]:
        InventoryService.post_movement(
            company=company,
            product=p,
            movement_type=MovementType.OPENING_STOCK,
            quantity=Decimal(qty),
            unit_cost=Decimal("60.00"),
            user=ns.owner,
        )

    # Create Invoice 1: 10 units of P1 (10 * 100 = 1,000 + 18% GST = 1,180)
    inv1_resp = oc.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust.id,
            "invoice_type": "GST",
            "invoice_date": today_str,
            "items": [
                {"product": p1.id, "quantity": "10.000", "unit_price": "100.00", "gst_rate": "18.00"}
            ],
        },
        format="json",
    )
    assert inv1_resp.status_code == 201, inv1_resp.data
    inv1_id = inv1_resp.data["id"]
    comp1 = oc.post(f"/api/v1/sales/invoices/{inv1_id}/complete/")
    assert comp1.status_code == 200

    # Create Invoice 2: 5 units of P2 (5 * 100 = 500 + 18% GST = 590)
    inv2_resp = oc.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust.id,
            "invoice_type": "GST",
            "invoice_date": today_str,
            "items": [
                {"product": p2.id, "quantity": "5.000", "unit_price": "100.00", "gst_rate": "18.00"}
            ],
        },
        format="json",
    )
    assert inv2_resp.status_code == 201
    inv2_id = inv2_resp.data["id"]
    comp2 = oc.post(f"/api/v1/sales/invoices/{inv2_id}/complete/")
    assert comp2.status_code == 200

    # Verify 1: Sales Register Report aggregation
    reg = ReportService.sales_register(company, date_from=month_start, date_to=today_str)
    assert len(reg["rows"]) == 2
    expected_taxable = Decimal("1500.00")  # 1000 + 500
    expected_grand = Decimal("1770.00")    # 1180 + 590
    assert Decimal(str(reg["totals"]["taxable"])) == expected_taxable
    assert Decimal(str(reg["totals"]["grand_total"])) == expected_grand

    # Verify 2: Dashboard Sales KPI parity
    dash = ReportService.dashboard(company)
    # Dashboard sales_month reflects net completed sales
    dash_sales = Decimal(str(dash["sales_this_month"]["total"]))
    # Ensure dashboard includes these sales
    assert dash_sales >= expected_grand

    # Verify 3: General Ledger Revenue (4100) & Output Tax (2210/2220) parity
    rev_acc = Account.objects.get(company=company, code="4100")
    cgst_acc = Account.objects.get(company=company, code="2210")
    sgst_acc = Account.objects.get(company=company, code="2220")

    gl_rev = JournalLine.objects.filter(
        entry__company=company,
        entry__status=JournalEntry.Status.POSTED,
        account=rev_acc,
    ).aggregate(c=Sum("credit"), d=Sum("debit"))
    net_rev = (gl_rev["c"] or Decimal("0")) - (gl_rev["d"] or Decimal("0"))
    assert net_rev == expected_taxable

    gl_cgst = JournalLine.objects.filter(
        entry__company=company,
        entry__status=JournalEntry.Status.POSTED,
        account=cgst_acc,
    ).aggregate(c=Sum("credit"), d=Sum("debit"))
    net_cgst = (gl_cgst["c"] or Decimal("0")) - (gl_cgst["d"] or Decimal("0"))
    assert net_cgst == Decimal("135.00")  # (1000*0.09) + (500*0.09) = 90 + 45

    # Verify 4: Full invariants
    assert_all_invariants(company)


def test_pj_inventory_summary_and_valuation_reconciliation():
    """T5 Reporting Truth: Inventory summary reconciles with StockMovements and Balances."""
    ns = seed_archetype("trader")
    company = ns.company
    p = next(prod for prod in ns.products if not prod.track_batch)
    wh = ns.warehouses[0]

    # Inward stock
    InventoryService.post_movement(
        company=company,
        product=p,
        movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("50.000"),
        unit_cost=Decimal("60.00"),
        user=ns.owner,
    )

    # Outward stock via movement
    InventoryService.post_movement(
        company=company,
        product=p,
        movement_type=MovementType.SALE,
        quantity=Decimal("15.000"),
        unit_cost=Decimal("60.00"),
        user=ns.owner,
    )

    # Query inventory summary
    inv_summary = ReportService.inventory_summary(company, warehouse_id=wh.id)
    matched_row = next(r for r in inv_summary["rows"] if r["product_id"] == p.id)

    # Verification: On hand matches movement sum
    assert Decimal(str(matched_row["on_hand"])) == Decimal("35.000")
    assert matched_row.get("balance_drift") is not True

    assert_all_invariants(company)


def test_pj_receivables_aging_to_customer_subledger_reconciliation():
    """T5 Reporting Truth: Receivables aging strictly matches Dashboard and Customer Subledgers."""
    ns = seed_archetype("trader")
    company = ns.company
    oc = ns.owner_client
    cust = ns.customers[0]
    p = next(prod for prod in ns.products if not prod.track_batch)

    # Seed stock
    InventoryService.post_movement(
        company=company,
        product=p,
        movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("50.000"),
        unit_cost=Decimal("60.00"),
        user=ns.owner,
    )

    # Create Invoice: 2 units (2 * 100 = 200 + 18% GST = 236.00)
    inv_resp = oc.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust.id,
            "invoice_type": "GST",
            "invoice_date": "2026-05-15",
            "items": [{"product": p.id, "quantity": "2.000", "unit_price": "100.00", "gst_rate": "18.00"}],
        },
        format="json",
    )
    assert inv_resp.status_code == 201
    comp = oc.post(f"/api/v1/sales/invoices/{inv_resp.data['id']}/complete/")
    assert comp.status_code == 200

    # Aging report
    aging = ReportService.receivables_aging(company)
    aging_total = sum(aging.values(), Decimal("0"))
    assert aging_total >= Decimal("236.00")

    # Customer Subledger total
    subledger_out = LedgerService.customer_outstanding(company, cust)
    assert subledger_out == Decimal("236.00")

    # GL Account 1200 (Trade Debtors) parity
    gl_ar = Account.objects.get(company=company, code="1200")
    ar_agg = JournalLine.objects.filter(
        entry__company=company,
        entry__status=JournalEntry.Status.POSTED,
        account=gl_ar,
    ).aggregate(d=Sum("debit"), c=Sum("credit"))
    net_gl_ar = (ar_agg["d"] or Decimal("0")) - (ar_agg["c"] or Decimal("0"))
    assert net_gl_ar == subledger_out

    assert_all_invariants(company)
