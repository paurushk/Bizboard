"""Phase 2 smoke: the invariant checks run against real posted state and pass.

This is the "does the invariant code even work" test — it exercises every
registered check against a company that has a completed sale and a completed
purchase, and asserts assert_all_invariants() does not raise. Real regressions
belong in tests/workflows/ and tests/regression/.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from core.invariants import (
    InvariantViolation,
    assert_all_invariants,
    registered,
    run_invariants,
)
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db


def test_registry_is_populated():
    names = registered()
    assert len(names) >= 15
    for domain in ("gl.", "gst.", "inventory.", "money.", "tenancy."):
        assert any(n.startswith(domain) for n in names), domain


def test_all_invariants_hold_for_a_fresh_company(tenant_a):
    # A company with no documents at all must still be fully consistent.
    failures = run_invariants(tenant_a.company)
    assert failures == {}, failures


def test_all_invariants_hold_after_a_completed_sale_and_purchase(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "20")
    customer = make_customer(tenant_a.company, gstin="29AAAAA0000A1ZY")
    supplier = make_supplier(tenant_a.company)

    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "3", "unit_price": "100.00", "gst_rate": "18"}],
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data

    pur = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "10", "unit_price": "80.00", "gst_rate": "18"}],
    )
    pdone = tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/")
    assert pdone.status_code == 200, pdone.data

    # The whole point: no invariant is violated by a normal sale + purchase.
    assert_all_invariants(tenant_a.company)


def test_isolation_between_two_tenants(tenant_a, tenant_b):
    for t in (tenant_a, tenant_b):
        p = make_product(t.company)
        add_stock(t, p, "5")
    assert run_invariants(tenant_a.company) == {}
    assert run_invariants(tenant_b.company) == {}


def test_plain_callables_hold_after_a_completed_sale(tenant_a):
    """The un-registered helper callables (called directly by WF chains) work
    against real posted state: numbering is gap-free, the lifecycle event is
    logged, no no-op money-audit rows."""
    from core.invariants.audit import money_mutations_logged, statutory_events_present
    from core.invariants.numbering import sequences_intact

    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "20")
    customer = make_customer(tenant_a.company, gstin="29AAAAA0000A1ZY")
    for _ in range(3):
        inv = create_draft_invoice(
            tenant_a, customer,
            [{"product": product.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "18"}],
        )
        assert tenant_a.client.post(
            f"/api/v1/sales/invoices/{inv['id']}/complete/"
        ).status_code == 200

    assert sequences_intact(tenant_a.company) == []
    assert statutory_events_present(tenant_a.company) == []
    assert money_mutations_logged(tenant_a.company) == []


def test_cross_reconcile_holds_after_a_completed_sale_and_purchase(tenant_a):
    """`reports.cross_reconcile` (§H7 callable) agrees TB / P&L / balance-sheet /
    stock-summary after a real books sale + purchase."""
    from core.invariants.reports import cross_reconcile

    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])

    product = make_product(company)
    add_stock(tenant_a, product, "20")
    customer = make_customer(company, gstin="29AAAAA0000A1ZY")
    supplier = make_supplier(company)

    inv = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "3", "unit_price": "100.00", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    pur = create_draft_purchase(
        tenant_a, supplier,
        [{"product": product.id, "quantity": "10", "unit_price": "80.00", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200

    assert cross_reconcile(company) == []


@pytest.mark.no_invariant_check  # this test deliberately leaves a broken journal
def test_the_sweep_actually_catches_a_broken_journal(tenant_a):
    """Red-then-green: a clean books company passes, then a hand-crafted
    unbalanced POSTED entry makes assert_all_invariants raise. Proof the sweep
    can fail — a gate that can only pass is worthless."""
    from accounting.models import Account, JournalEntry, JournalLine
    from accounting.services import seed_chart_of_accounts

    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(company)
    assert_all_invariants(company)  # green

    cash = Account.objects.get(company=company, code="1100")
    sales = Account.objects.get(company=company, code="4100")
    entry = JournalEntry.objects.create(
        company=company, entry_date=date(2026, 6, 1), status=JournalEntry.Status.POSTED,
        narration="deliberately unbalanced", created_by=tenant_a.owner,
    )
    JournalLine.objects.create(company=company, entry=entry, account=cash,
                               debit=Decimal("100.00"), credit=Decimal("0"))
    JournalLine.objects.create(company=company, entry=entry, account=sales,
                               debit=Decimal("0"), credit=Decimal("90.00"))

    with pytest.raises(InvariantViolation):
        assert_all_invariants(company)  # red


def test_sequences_intact_flags_a_gap(tenant_a):
    """Deleting the middle completed invoice leaves a numbering gap the callable
    detects (proves it can actually fail)."""
    from core.invariants.numbering import sequences_intact
    from sales.models import SalesInvoice

    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "20")
    customer = make_customer(tenant_a.company, gstin="29AAAAA0000A1ZY")
    ids = []
    for _ in range(3):
        inv = create_draft_invoice(
            tenant_a, customer,
            [{"product": product.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "18"}],
        )
        tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
        ids.append(inv["id"])

    assert sequences_intact(tenant_a.company) == []
    SalesInvoice.objects.filter(pk=ids[1]).delete()
    problems = sequences_intact(tenant_a.company)
    assert problems and "gap" in problems[0].lower(), problems
