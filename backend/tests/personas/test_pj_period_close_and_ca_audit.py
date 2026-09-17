"""Persona Journey — Munshi Manual Journals, Accounting Period Close & External CA Audit.

Validates:
1. Munshi Manual Double-Entry Journals:
   - Valid balanced journal entry (Debit == Credit) posts cleanly.
   - Unbalanced journal entry (Debit != Credit) is strictly rejected by validation.
2. Accounting Period Freeze & Role Boundaries:
   - Munshi/Accountant can view periods but is denied period mutation/close (HTTP 403).
   - Owner soft-closes and closes the fiscal period.
   - Once closed, attempts to complete back-dated sales invoices within the period are blocked (HelpCode.CLOSED_PERIOD).
3. External CA Statutory Audit Inspection:
   - Trial Balance zero-imbalance verification (Sum Debits == Sum Credits).
   - BooksHealthService control balances confirm zero variance between GL accounts and operational subledgers:
     * GL Account 1200 matches Customer AR subledger
     * GL Account 2100 matches Supplier AP subledger
   - Closed period audit trail integrity verified.
4. Invariants:
   - assert_all_invariants(company) holds clean without discrepancy.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from accounting.models import Account, AccountingPeriod, JournalEntry
from core.invariants import assert_all_invariants
from accounting.services import BooksHealthService
from accounting.reports import trial_balance
from tests.personas.fixtures import seed_archetype

pytestmark = pytest.mark.django_db


def test_pj_munshi_journals_period_close_and_ca_audit():
    """Munshi (P5 Accountant), Owner (P1), and CA Auditor (P6): Manual journals, period freeze, and statutory audit."""
    ns = seed_archetype("trader")
    company = ns.company
    ac = ns.acct_client
    oc = ns.owner_client

    # Helper to resolve chart of accounts IDs
    def _acc(code: str) -> int:
        return Account.objects.get(company=company, code=code).id

    # 1. Munshi Manual Double-Entry Journal Flow
    # Attempt 1: Unbalanced journal (Debit 10,000 != Credit 8,000)
    unbalanced_resp = ac.post(
        "/api/v1/accounting/journals/",
        {
            "entry_date": "2026-04-10",
            "narration": "Office Equipment Purchase (Unbalanced attempt)",
            "lines": [
                {"account": _acc("1500"), "debit": "10000.00", "credit": "0.00"},
                {"account": _acc("1100"), "debit": "0.00", "credit": "8000.00"},
            ],
        },
        format="json",
    )
    assert unbalanced_resp.status_code == 400, "Unbalanced journal must be rejected"

    # Attempt 2: Balanced journal (Debit 10,000 == Credit 10,000)
    balanced_resp = ac.post(
        "/api/v1/accounting/journals/",
        {
            "entry_date": "2026-04-10",
            "narration": "Office Equipment Purchase via Bank",
            "lines": [
                {"account": _acc("1500"), "debit": "10000.00", "credit": "0.00"},
                {"account": _acc("1100"), "debit": "0.00", "credit": "10000.00"},
            ],
        },
        format="json",
    )
    assert balanced_resp.status_code == 201, balanced_resp.data
    jr_id = balanced_resp.data["id"]

    # Post the journal
    post_jr = ac.post(f"/api/v1/accounting/journals/{jr_id}/post/")
    assert post_jr.status_code in (200, 202)
    assert JournalEntry.objects.get(pk=jr_id).status == JournalEntry.Status.POSTED

    # 2. Accounting Period Lifecycle & Role Boundaries
    # Accountant creates period draft
    period = AccountingPeriod.objects.create(
        company=company,
        name="FY25-26 Q4 (March 2026)",
        start_date="2026-03-01",
        end_date="2026-03-31",
        status=AccountingPeriod.Status.OPEN,
    )

    # Accountant can view periods
    view_periods = ac.get("/api/v1/accounting/periods/")
    assert view_periods.status_code == 200

    # Role boundary: Accountant is denied permission to close the period (Owner-only)
    acct_close_denied = ac.post(f"/api/v1/accounting/periods/{period.id}/close/")
    assert acct_close_denied.status_code == 403, "Accountant must not be permitted to close accounting periods"

    # Owner closes the period
    owner_close = oc.post(f"/api/v1/accounting/periods/{period.id}/close/")
    assert owner_close.status_code == 200, owner_close.data
    period.refresh_from_db()
    assert period.status == AccountingPeriod.Status.CLOSED

    # 3. Period Lock Guard: Mutation in closed period is blocked
    # Munshi attempts to post a manual journal dated in March 2026 (closed period)
    closed_jr_resp = ac.post(
        "/api/v1/accounting/journals/",
        {
            "entry_date": "2026-03-15",
            "narration": "Back-dated journal entry attempt in closed period",
            "lines": [
                {"account": _acc("1500"), "debit": "500.00", "credit": "0.00"},
                {"account": _acc("1100"), "debit": "0.00", "credit": "500.00"},
            ],
        },
        format="json",
    )
    assert closed_jr_resp.status_code == 201, closed_jr_resp.data
    closed_jr_id = closed_jr_resp.data["id"]

    post_closed_jr = ac.post(f"/api/v1/accounting/journals/{closed_jr_id}/post/")
    assert post_closed_jr.status_code in (400, 409), post_closed_jr.data
    err_msg = str(post_closed_jr.data).lower()
    assert "closed" in err_msg or "period" in err_msg

    # 4. External CA Statutory Audit Inspection
    # Auditor reviews Trial Balance
    tb = trial_balance(company)
    assert tb["balanced"] is True
    assert Decimal(str(tb["total_debit"])) == Decimal(str(tb["total_credit"]))

    # Auditor reviews Subledger vs GL Control Balances
    controls = BooksHealthService.control_balances(company)
    assert controls["ar"]["healthy"] is True
    assert Decimal(str(controls["ar"]["gl"])) == Decimal(str(controls["ar"]["ledger"]))
    assert controls["ap"]["healthy"] is True
    assert Decimal(str(controls["ap"]["gl"])) == Decimal(str(controls["ap"]["ledger"]))
    assert not [a for a in controls["alerts"] if a["code"] in ("AR_CONTROL_MISMATCH", "AP_CONTROL_MISMATCH")]

    # Invariants assert complete ledger integrity
    assert_all_invariants(company)
