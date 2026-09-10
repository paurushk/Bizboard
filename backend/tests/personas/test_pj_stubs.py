"""Persona journeys not yet implemented — each is a spec.

Implement by replacing the body with the journey (seed_archetype -> drive the
persona's client -> boundary.allowed / boundary.denied -> assert_all_invariants),
and delete the skip. See tests/personas/README.md for the matrix.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db

_TODO = "persona journey not yet implemented — see docstring / README"


@pytest.mark.skip(reason=_TODO)
def test_pj_trader_sales_staff_boundary():
    """SALES_STAFF at a trader: create quotation + invoice + receipt for a GSTIN
    customer; denied cancel, journals, imports, adjustments, financial reports."""


@pytest.mark.skip(reason=_TODO)
def test_pj_trader_accountant_day():
    """ACCOUNTANT: post a manual JV, do a bank reconciliation, view P&L/BS, run
    FY close; denied create-sales, manage-inventory, import. Books stay balanced."""


@pytest.mark.skip(reason=_TODO)
def test_pj_trader_viewer_readonly():
    """VIEWER: every list/detail GET in scope is 200; every mutation is 403;
    financial reports are 403 by default (BUG-319)."""


@pytest.mark.skip(reason=_TODO)
def test_pj_trader_import_operator():
    """A SALES_STAFF + can_import user: bulk-import products / customers / opening
    stock; re-running the same import creates nothing twice; denied non-import
    mutations."""


@pytest.mark.skip(reason=_TODO)
def test_pj_wholesale_owner_multi_godown_day():
    """WHOLESALE owner: receive stock into 3 godowns, transfer between them
    (TRANSFER_OUT + TRANSFER_IN net zero), sell from a branch, run dunning on an
    overdue invoice, close the period. Invariant sweep clean."""


@pytest.mark.skip(reason=_TODO)
def test_pj_wholesale_accountant_period_close():
    """WHOLESALE accountant: reconcile the bank, review the trial balance and
    ageing, close the month; a back-dated posting into the closed month is
    rejected."""


@pytest.mark.skip(reason=_TODO)
def test_pj_service_owner_no_stock():
    """SERVICE owner: raise GST invoices for non-stock items -> no StockMovement
    ever created, GL still balances, receipts allocate normally."""


@pytest.mark.skip(reason=_TODO)
def test_pj_newuser_register_to_first_invoice():
    """Register -> guided /setup -> create item + customer -> first invoice ->
    receipt. The registrant is OWNER; the dashboard checklist advances."""


@pytest.mark.skip(reason=_TODO)
def test_pj_migration_wholesale_large_cutover_with_history():
    """As PJ-MIGRATION-TRADER but multi-godown opening stock, more parties, and a
    batch of open (unpaid) invoices/bills as of the cutover date; opening_ties_out
    holds; a mid-import failure resumes without doubling."""
