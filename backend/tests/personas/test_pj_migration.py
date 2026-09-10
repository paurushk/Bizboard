"""PJ-MIGRATION-TRADER — a business moving to BizBoard with its own data.

The day-zero cutover: load item master, parties, opening stock (per godown, with
cost), the opening trial balance, and party-wise opening balances -- then
RECONCILE: computed sub-ledgers must equal the control accounts in the opening
TB, and inventory control must equal the opening-stock valuation. Then a first
live invoice continues the old numbering series. Then a redo of a wrong opening.

Uses direct API calls for the load (the CSV-parser idempotency is WF-15/23/24/25);
the point here is the reconciliation gate.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.invariants import assert_all_invariants
from core.invariants.reports import opening_ties_out
from tests.personas.fixtures import seed_archetype

pytestmark = pytest.mark.django_db


def _acct(company, code):
    from accounting.models import Account

    return company.accounts.get(code=code).id if hasattr(company, "accounts") else \
        Account.objects.get(company=company, code=code).id


def _post_journal(client, entry_date, lines):
    r = client.post(
        "/api/v1/accounting/journals/",
        {"entry_date": entry_date, "narration": "opening", "lines": lines},
        format="json",
    )
    assert r.status_code == 201, r.data
    jid = r.data["id"]
    p = client.post(f"/api/v1/accounting/journals/{jid}/post/")
    assert p.status_code in (200, 202), p.data
    return jid


def test_pj_migration_trader_cutover_and_reconcile():
    ns = seed_archetype("migration")
    company, oc = ns.company, ns.owner_client
    from accounting.models import Account, JournalEntry
    from inventory.models import MovementType
    from inventory.services import InventoryService
    from masters.models import Customer, Product, Supplier

    CUTOVER = "2026-04-01"

    # --- 1. numbering series continues from the old system (last was SI-000100) ---
    ns_resp = oc.patch(
        "/api/v1/sales/invoices/number-series/",
        {"prefix": "SI", "next_number": 101, "padding": 6}, format="json",
    )
    assert ns_resp.status_code == 200, ns_resp.data

    # --- 2. item master + parties ---
    items = [
        Product.objects.create(company=company, name=f"Item {i}", sku=f"MIG-{i:03d}",
                               gst_rate=Decimal("18"), purchase_price=Decimal("50"),
                               selling_price=Decimal("80"))
        for i in range(6)
    ]
    debtor = Customer.objects.create(company=company, name="Old Debtor", state="Karnataka",
                                     gstin="29AAAAA0001A1Z5")
    creditor = Supplier.objects.create(company=company, name="Old Creditor", state="Karnataka",
                                       gstin="29ZZZZZ0001A1Z5")

    # --- 3. opening stock: 6 items x 100 units @ 50 = 30,000 valuation ---
    for it in items:
        InventoryService.post_movement(
            company=company, product=it, movement_type=MovementType.OPENING_STOCK,
            quantity=Decimal("100"), unit_cost=Decimal("50"), user=ns.owner,
        )
    opening_valuation = Decimal("30000.00")  # 6 * 100 * 50

    # --- 4. opening trial balance JV ---
    #   Dr Cash 1100        20,000
    #   Dr Bank 1500        40,000
    #   Dr Inventory 1400   30,000
    #   Dr Debtors 1200     12,000   (customer-tagged)
    #                    Cr Creditors 2100     8,000   (supplier-tagged)
    #                    Cr Opening Equity 3200 94,000
    oe = Account.objects.filter(company=company, code="3200").first() or Account.objects.create(
        company=company, code="3200", name="Opening Balance Equity", type="EQUITY"
    )
    _post_journal(oc, CUTOVER, [
        {"account": _acct(company, "1100"), "debit": "20000.00", "credit": "0"},
        {"account": _acct(company, "1500"), "debit": "40000.00", "credit": "0"},
        {"account": _acct(company, "1400"), "debit": "30000.00", "credit": "0"},
        {"account": _acct(company, "1200"), "debit": "12000.00", "credit": "0", "customer": debtor.id},
        {"account": _acct(company, "2100"), "debit": "0", "credit": "8000.00", "supplier": creditor.id},
        {"account": oe.id, "debit": "0", "credit": "94000.00"},
    ])

    # --- 5. RECONCILE — the gate ---
    problems = opening_ties_out(company)
    assert not problems, problems
    from accounting.reports import trial_balance

    assert trial_balance(company)["balanced"]
    assert_all_invariants(company)

    # --- 6. first live invoice continues the series ---
    inv = oc.post(
        "/api/v1/sales/invoices/",
        {"customer": debtor.id, "invoice_type": "GST",
         "items": [{"product": items[0].id, "quantity": "2", "unit_price": "80.00", "gst_rate": "18"}]},
        format="json",
    )
    assert inv.status_code == 201, inv.data
    done = oc.post(f"/api/v1/sales/invoices/{inv.data['id']}/complete/")
    assert done.status_code == 200, done.data
    num = done.data["number"]
    assert num.endswith("000101") and "SI" in num, f"series did not continue: {num}"

    assert_all_invariants(company)


def test_pj_migration_redo_wrong_opening(assert_consistent=None):
    """The owner realises the opening TB was wrong: reverse it and re-post.
    Invariants hold before and after."""
    ns = seed_archetype("migration")
    company, oc = ns.company, ns.owner_client
    from accounting.models import Account, JournalEntry

    oe = Account.objects.filter(company=company, code="3200").first() or Account.objects.create(
        company=company, code="3200", name="Opening Balance Equity", type="EQUITY"
    )
    # wrong opening
    jid = _post_journal(oc, "2026-04-01", [
        {"account": _acct(company, "1100"), "debit": "5000.00", "credit": "0"},
        {"account": oe.id, "debit": "0", "credit": "5000.00"},
    ])
    assert_all_invariants(company)

    # reverse it
    rev = oc.post(f"/api/v1/accounting/journals/{jid}/reverse/")
    assert rev.status_code in (200, 201, 202), rev.data
    je = JournalEntry.objects.get(pk=jid)
    assert je.status == JournalEntry.Status.REVERSED

    # re-post the correct one
    _post_journal(oc, "2026-04-01", [
        {"account": _acct(company, "1100"), "debit": "8000.00", "credit": "0"},
        {"account": oe.id, "debit": "0", "credit": "8000.00"},
    ])
    from accounting.reports import trial_balance

    assert trial_balance(company)["balanced"]
    assert_all_invariants(company)
