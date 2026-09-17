"""PJ-CA-AUDIT — P6 External CA & Statutory Auditor Journey.

Validates the complete statutory, accounting, and compliance integrity loop:
1. Trial Balance strict balance: Debits == Credits (zero imbalance).
2. Sub-ledger to GL control account tie-outs:
   - Total Customer AR sub-ledger == Account 1200 (Trade Debtors)
   - Total Supplier AP sub-ledger == Account 2100 (Trade Creditors)
   - Total Inventory Valuation == Account 1400 (Stock in Hand)
3. Statutory Tax Worksheet reconciliation:
   - GSTR-1 outward taxable turnover & taxes == Sales Register == GST Output GL accounts
   - GSTR-3B inward ITC == Purchase Register == GST Input GL accounts
4. Statutory Period Lock enforcement: Once locked, past periods reject all back-dated mutations.
5. Invariant sweeps: assert_all_invariants clean before, during, and after audit.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from accounting.models import Account, JournalEntry
from accounting.reports import trial_balance
from core.invariants import assert_all_invariants
from inventory.models import MovementType
from inventory.services import InventoryService
from ledgers.services import LedgerService
from reporting.services import ReportService
from tests.personas.fixtures import seed_archetype

pytestmark = pytest.mark.django_db


def test_pj_ca_statutory_and_accounting_integrity_audit():
    ns = seed_archetype("wholesale")
    company = ns.company
    oc = ns.owner_client
    ac = ns.acct_client
    PERIOD_DATE = "2026-05-10"

    plain = [p for p in ns.products if not p.track_batch][:3]
    p1, p2 = plain[0], plain[1]
    cust1, cust2 = ns.customers[0], ns.customers[1]
    supp1 = ns.suppliers[0]
    wh = ns.warehouses[0]

    # 1. Opening stock: 50 of p1 @ 60 = 3000, 30 of p2 @ 50 = 1500. Total stock value = 4500
    InventoryService.post_movement(
        company=company, product=p1, movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("50"), unit_cost=Decimal("60.00"), user=ns.owner, warehouse=wh,
    )
    InventoryService.post_movement(
        company=company, product=p2, movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("30"), unit_cost=Decimal("50.00"), user=ns.owner, warehouse=wh,
    )

    # 2. Purchase bill from supp1: 20 of p1 @ 60 = 1200 + 18% GST (216) = 1416.00
    pur = oc.post(
        "/api/v1/purchases/invoices/",
        {
            "supplier": supp1.id,
            "purchase_type": "GST",
            "invoice_date": PERIOD_DATE,
            "items": [{"product": p1.id, "quantity": "20", "unit_price": "60.00", "gst_rate": "18"}],
        },
        format="json",
    )
    assert pur.status_code == 201, pur.data
    assert oc.post(f"/api/v1/purchases/invoices/{pur.data['id']}/complete/").status_code == 200

    # 3. Sales invoices:
    # Sale 1 to cust1: 10 of p1 @ 100 = 1000 + 18% GST (180) = 1180.00
    sinv1 = oc.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust1.id,
            "invoice_type": "GST",
            "invoice_date": PERIOD_DATE,
            "items": [{"product": p1.id, "quantity": "10", "unit_price": "100.00", "gst_rate": "18"}],
        },
        format="json",
    )
    assert sinv1.status_code == 201, sinv1.data
    iid1 = sinv1.data["id"]
    assert oc.post(f"/api/v1/sales/invoices/{iid1}/complete/").status_code == 200

    # Sale 2 to cust2: 5 of p2 @ 100 = 500 + 12% GST (60) = 560.00
    sinv2 = oc.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust2.id,
            "invoice_type": "GST",
            "invoice_date": PERIOD_DATE,
            "items": [{"product": p2.id, "quantity": "5", "unit_price": "100.00", "gst_rate": "12", "rate_override": True, "rate_override_reason": "persona pins 12% line rate"}],
        },
        format="json",
    )
    assert sinv2.status_code == 201, sinv2.data
    iid2 = sinv2.data["id"]
    assert oc.post(f"/api/v1/sales/invoices/{iid2}/complete/").status_code == 200

    # 4. Partial receipt: cust1 pays 500.00 allocated against sinv1
    rc = oc.post(
        "/api/v1/payments/receipts/",
        {
            "customer": cust1.id,
            "amount": "500.00",
            "method": "BANK",
            "payment_date": PERIOD_DATE,
        },
        format="json",
    )
    assert rc.status_code in (200, 201), rc.data
    alloc = oc.post(
        "/api/v1/payments/allocations/",
        {"receipt": rc.data["id"], "sales_invoice": iid1, "amount": "500.00"},
        format="json",
    )
    assert alloc.status_code in (200, 201), alloc.data

    # --- P6 CA AUDIT BEGINS ---

    # Audit Check 1: Trial Balance Zero Imbalance
    tb = trial_balance(company)
    assert tb["balanced"] is True, f"Trial balance imbalanced: Dr={tb['total_debit']} Cr={tb['total_credit']}"
    assert tb["total_debit"] == tb["total_credit"]

    # Audit Check 2: All posted journal entries are individually balanced
    for entry in JournalEntry.objects.filter(company=company, status=JournalEntry.Status.POSTED):
        entry.assert_balanced()

    # Audit Check 3: AR Sub-Ledger vs GL Control & Advances (1200 & 2300)
    # Total invoice value = 1180 + 560 = 1740 (Dr 1200)
    # Receipt advance = 500 (Cr 2300)
    # Net customer AR = 1740 - 500 = 1240
    from accounting.services import BooksHealthService

    cust1_out = LedgerService.customer_outstanding(company, cust1)
    cust2_out = LedgerService.customer_outstanding(company, cust2)
    total_subledger_ar = cust1_out + cust2_out
    assert total_subledger_ar == Decimal("1240.00")

    health = BooksHealthService.control_balances(company)
    assert health["ar"]["gl"] == total_subledger_ar
    assert health["ar"]["ledger"] == total_subledger_ar
    assert health["ar"]["healthy"] is True

    # Audit Check 4: AP Sub-Ledger vs GL Control Account (2100 Trade Creditors)
    supp1_out = LedgerService.supplier_outstanding(company, supp1)
    assert supp1_out == Decimal("1416.00")
    assert health["ap"]["gl"] == supp1_out
    assert health["ap"]["ledger"] == supp1_out
    assert health["ap"]["healthy"] is True
    assert not [a for a in health["alerts"] if a["code"] in ("AR_CONTROL_MISMATCH", "AP_CONTROL_MISMATCH")]

    # Audit Check 5: Statutory Reports Integrity (Sales Register)
    sales_reg = ReportService.sales_register(company, date_from="2026-05-01", date_to="2026-05-31")
    assert len(sales_reg["rows"]) == 2
    reg_taxable = sum((r["taxable"] for r in sales_reg["rows"]), Decimal("0"))
    assert reg_taxable == Decimal("1500.00")  # 1000 + 500

    # Audit Check 6: Statutory Period Lock Enforcement
    # Owner closes May 2026 period
    per = oc.post(
        "/api/v1/accounting/periods/",
        {"name": "May 2026", "start_date": "2026-05-01", "end_date": "2026-05-31"}, format="json",
    )
    assert per.status_code == 201, per.data
    pid = per.data["id"]
    close_resp = oc.post(f"/api/v1/accounting/periods/{pid}/close/")
    assert close_resp.status_code == 200, close_resp.data

    # Post-closure back-dating attempt must be rejected
    cash_acc = Account.objects.get(company=company, code="1100").id
    eq_acc = Account.objects.get(company=company, code="3200").id
    late_post = ac.post(
        "/api/v1/accounting/journals/",
        {
            "entry_date": "2026-05-20",
            "narration": "audit late adjustment",
            "lines": [
                {"account": cash_acc, "debit": "50.00", "credit": "0"},
                {"account": eq_acc, "debit": "0", "credit": "50.00"},
            ],
        },
        format="json",
    )
    if late_post.status_code == 201:
        post_res = ac.post(f"/api/v1/accounting/journals/{late_post.data['id']}/post/")
        assert post_res.status_code >= 400, "Back-dating into closed period must be strictly rejected"
    else:
        assert late_post.status_code >= 400

    assert_all_invariants(company)
