"""ACS-71: query budgets for the accounting list screens.

Time budgets belong on a production-sized database; what a unit test can hold is the number of queries,
which must not grow with the number of rows (no per-row lookups).
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounting.models import Account, AccountingPeriod, CostCenter, Expense
from accounting.services import PostingService
from masters.models import ExpenseCategory
from tests.test_sprint_a_accounting_p1 import books  # noqa: F401

pytestmark = pytest.mark.django_db


def _acct(books, code):  # noqa: F811
    return Account.objects.get(company=books.company, code=code)


def _queries(client, url, params=None):
    with CaptureQueriesContext(connection) as ctx:
        resp = client.get(url, params or {})
    assert resp.status_code == 200, resp.content[:300]
    return len(ctx)


def _seed_journals(books, n):  # noqa: F811
    cash, sales = _acct(books, "1100"), _acct(books, "4100")
    for i in range(n):
        PostingService.post(
            company=books.company, source_type="TEST", source_id=10_000 + i, purpose="X",
            entry_date=date(2026, 6, 1) + timedelta(days=i % 28), user=books.owner, narration=f"n{i}",
            lines=[{"account": cash, "debit": Decimal("1")}, {"account": sales, "credit": Decimal("1")}],
        )


def test_journal_register_query_count_does_not_grow_with_rows(books):  # noqa: F811
    _seed_journals(books, 5)
    few = _queries(books.client, "/api/v1/accounting/journals/", {"page_size": 50})
    _seed_journals(books, 60)
    many = _queries(books.client, "/api/v1/accounting/journals/", {"page_size": 50})
    assert many <= few + 2, (few, many)


def test_chart_with_balances_is_a_fixed_number_of_queries(books):  # noqa: F811
    few = _queries(books.client, "/api/v1/accounting/accounts/", {"with_balance": "1", "page_size": 200})
    for n in range(40):
        Account.objects.create(company=books.company, code=f"7{n:03d}", name=f"Extra {n}", type="EXPENSE")
    many = _queries(books.client, "/api/v1/accounting/accounts/", {"with_balance": "1", "page_size": 200})
    assert many <= few + 2, (few, many)


def test_day_book_ledger_query_count_is_flat(books):  # noqa: F811
    _seed_journals(books, 3)
    few = _queries(books.client, "/api/v1/reports/day-book/ledger/", {"date_from": "2026-06-01", "date_to": "2026-06-28", "page_size": 100})
    _seed_journals(books, 80)
    many = _queries(books.client, "/api/v1/reports/day-book/ledger/", {"date_from": "2026-06-01", "date_to": "2026-06-28", "page_size": 100})
    assert many <= few + 3, (few, many)


def test_expense_register_query_count_is_flat(books):  # noqa: F811
    cat = ExpenseCategory.objects.create(company=books.company, name="Tea")
    cc = CostCenter.objects.create(company=books.company, code="S", name="Shop")

    def add(n):
        for i in range(n):
            Expense.objects.create(
                company=books.company, category=cat, expense_date=date(2026, 6, 1), amount=Decimal("1"),
                number=f"E{Expense.objects.count()}-{i}", cost_center=cc, created_by=books.owner, updated_by=books.owner,
            )

    add(3)
    few = _queries(books.client, "/api/v1/accounting/expenses/", {"page_size": 100})
    add(60)
    many = _queries(books.client, "/api/v1/accounting/expenses/", {"page_size": 100})
    assert many <= few + 2, (few, many)


def test_close_summary_is_cheap_and_flat(books):  # noqa: F811
    for m in range(1, 7):
        AccountingPeriod.objects.create(
            company=books.company, name=f"M{m}", start_date=date(2026, m, 1), end_date=date(2026, m, 28),
        )
    few = _queries(books.client, "/api/v1/accounting/periods/close-summary/")
    for m in range(7, 13):
        AccountingPeriod.objects.create(
            company=books.company, name=f"M{m}", start_date=date(2026, m, 1), end_date=date(2026, m, 28),
        )
    many = _queries(books.client, "/api/v1/accounting/periods/close-summary/")
    assert many <= few + 2, (few, many)
