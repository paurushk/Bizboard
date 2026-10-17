"""ACS-72: the accounting paths that must hold when two people (or one double click) hit them at once.

SQLite does not enforce row locks, so these run only against PostgreSQL:
double post, double create with one token, double dispose, double void, two matches of one bank line,
a period close racing a journal post.
"""
from __future__ import annotations

import threading
from datetime import date
from decimal import Decimal

import pytest
from django.db import connection
from rest_framework.test import APIClient

from accounting import bank_match
from accounting.models import Account, AccountingPeriod, BankReconSession, FixedAsset, JournalEntry, JournalLine
from accounting.services import PostingService
from masters.models import ExpenseCategory
from payments.models import BankAccount, BankStatement, BankStatementLine
from tests.test_sprint_a_accounting_p1 import books  # noqa: F401

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.postgres]

J = "/api/v1/accounting/journals/"


def _require_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row-level locking (select_for_update)")


def _race(tenant, calls):
    """Run each call(client) at the same instant on its own thread and connection; return the results."""
    barrier = threading.Barrier(len(calls), timeout=15)
    results: list = [None] * len(calls)

    def runner(index, call):
        connection.close()
        client = APIClient()
        client.force_authenticate(user=tenant.owner)
        try:
            barrier.wait()
            results[index] = call(client)
        except Exception as exc:  # pragma: no cover - reported by the assertion that follows
            results[index] = exc
        finally:
            connection.close()

    threads = [threading.Thread(target=runner, args=(i, c)) for i, c in enumerate(calls)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results


def _statuses(results):
    for r in results:
        assert not isinstance(r, Exception), r
    return sorted(r.status_code for r in results)


def _acct(books, code):  # noqa: F811
    return Account.objects.get(company=books.company, code=code)


def _draft(books, **extra):  # noqa: F811
    body = {
        "entry_date": date(2026, 6, 10).isoformat(),
        "narration": "race",
        "lines": [
            {"account": _acct(books, "5400").id, "debit": "100.00", "credit": "0"},
            {"account": _acct(books, "1100").id, "debit": "0", "credit": "100.00"},
        ],
        **extra,
    }
    resp = APIClient()
    resp.force_authenticate(user=books.owner)
    out = resp.post(J, body, format="json")
    assert out.status_code in (200, 201), out.data
    return out


def test_double_post_of_one_draft_posts_once(books):  # noqa: F811
    _require_postgres()
    draft = _draft(books).data["id"]
    results = _race(books, [lambda c: c.post(f"{J}{draft}/post/")] * 2)
    assert _statuses(results) == [200, 400]
    entry = JournalEntry.objects.get(pk=draft)
    assert entry.status == JournalEntry.Status.POSTED
    assert JournalLine.objects.filter(entry=entry).count() == 2


def test_two_creates_with_one_token_make_one_draft(books):  # noqa: F811
    _require_postgres()
    body = {
        "entry_date": "2026-06-10",
        "lines": [
            {"account": _acct(books, "5400").id, "debit": "5.00", "credit": "0"},
            {"account": _acct(books, "1100").id, "debit": "0", "credit": "5.00"},
        ],
        "client_token": "race-token-1",
    }
    results = _race(books, [lambda c: c.post(J, body, format="json")] * 2)
    codes = _statuses(results)
    # One create wins; the other either returns the first draft or loses on the unique token.
    assert codes[0] in (200, 201) and JournalEntry.objects.filter(company=books.company, client_token="race-token-1").count() == 1


def test_double_dispose_posts_one_disposal(books):  # noqa: F811
    _require_postgres()
    asset = FixedAsset.objects.create(
        company=books.company, name="Race asset", asset_account=_acct(books, "1600"),
        accumulated_depreciation_account=_acct(books, "1650"), depreciation_expense_account=_acct(books, "5300"),
        acquisition_date=date(2026, 1, 1), acquisition_cost=Decimal("1000.00"), useful_life_months=12,
    )
    from django.test import override_settings

    with override_settings(ENABLE_FIXED_ASSETS=True):
        results = _race(
            books,
            [lambda c: c.post(f"/api/v1/accounting/fixed-assets/{asset.id}/dispose/", {"confirm": True, "disposal_date": "2026-06-01"}, format="json")] * 2,
        )
    assert _statuses(results) == [200, 400]
    assert JournalEntry.objects.filter(company=books.company, source_type="FIXED_ASSET", source_id=asset.id, purpose="DISPOSAL").count() == 1


def test_double_void_of_an_expense_reverses_once(books):  # noqa: F811
    _require_postgres()
    books.company.expense_gl_start_date = date(2026, 1, 1)
    books.company.save(update_fields=["expense_gl_start_date"])
    cat = ExpenseCategory.objects.create(company=books.company, name="Tea")
    client = APIClient()
    client.force_authenticate(user=books.owner)
    created = client.post("/api/v1/accounting/expenses/", {"category": cat.id, "expense_date": "2026-06-02", "amount": "30"}, format="json")
    assert created.status_code == 201
    eid = created.data["id"]
    results = _race(books, [lambda c: c.post(f"/api/v1/accounting/expenses/{eid}/void/", {"reason": "dup"}, format="json")] * 2)
    assert _statuses(results) == [200, 400]
    reversals = JournalEntry.objects.filter(company=books.company, source_type="JOURNAL_REVERSAL").count()
    assert reversals == 1


def test_two_people_matching_one_bank_line_get_one_winner(books):  # noqa: F811
    _require_postgres()
    bank = BankAccount.objects.create(company=books.company, name="HDFC")
    ledger = PostingService._bank_gl_account(books.company, bank)
    statement = BankStatement.objects.create(company=books.company, bank_account=bank, period_end=date(2026, 6, 30))
    line = BankStatementLine.objects.create(company=books.company, statement=statement, txn_date=date(2026, 6, 6), amount=Decimal("100"))
    ids = []
    for n in range(2):
        entry = PostingService.post(
            company=books.company, source_type="TEST", source_id=500 + n, purpose="X", entry_date=date(2026, 6, 5), user=books.owner,
            lines=[{"account": ledger, "debit": Decimal("100")}, {"account": _acct(books, "4100"), "credit": Decimal("100")}],
        )
        ids.append(entry.lines.get(account=ledger).id)
    session = BankReconSession.objects.create(
        company=books.company, account=ledger, statement=statement, statement_date=date(2026, 6, 30),
    )
    base = f"/api/v1/accounting/bank-recon-sessions/{session.id}/match/"
    results = _race(books, [
        lambda c, j=ids[0]: c.post(base, {"journal_line": j, "bank_statement_line": line.id}, format="json"),
        lambda c, j=ids[1]: c.post(base, {"journal_line": j, "bank_statement_line": line.id}, format="json"),
    ])
    assert _statuses(results) == [200, 400]
    assert JournalLine.objects.filter(bank_statement_line=line).count() == 1
    assert bank_match.inconsistent_lines(books.company) == []


def test_closing_a_month_while_a_journal_posts_never_leaves_a_late_entry(books):  # noqa: F811
    _require_postgres()
    period = AccountingPeriod.objects.create(
        company=books.company, name="Jun", start_date=date(2026, 6, 1), end_date=date(2026, 6, 30),
    )
    draft = _draft(books).data["id"]
    results = _race(books, [
        lambda c: c.post(f"/api/v1/accounting/periods/{period.id}/close/"),
        lambda c: c.post(f"{J}{draft}/post/"),
    ])
    for r in results:
        assert not isinstance(r, Exception), r
        assert r.status_code < 500
    period.refresh_from_db()
    entry = JournalEntry.objects.get(pk=draft)
    if period.status == AccountingPeriod.Status.CLOSED and entry.status == JournalEntry.Status.POSTED:
        # The post got in first: it must be stamped before the close was saved.
        assert entry.posted_at <= period.updated_at
