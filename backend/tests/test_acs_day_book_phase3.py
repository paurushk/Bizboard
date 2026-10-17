"""ACS-60: ledger Day Book and the corrected daily cash summary."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from accounting.models import Account, CostCenter, Expense, JournalEntry
from accounting.services import PostingService
from masters.models import ExpenseCategory
from reporting import day_book as ledger
from tests.test_sprint_a_accounting_p1 import books  # noqa: F401

pytestmark = pytest.mark.django_db

L = "/api/v1/reports/day-book/ledger/"
C = "/api/v1/reports/day-book/"


def _acct(books, code):  # noqa: F811
    return Account.objects.get(company=books.company, code=code)


def _post(books, sid, day, debit_code, credit_code, amount, **kw):  # noqa: F811
    return PostingService.post(
        company=books.company, source_type=kw.pop("source_type", "TEST"), source_id=sid, purpose=kw.pop("purpose", "X"),
        entry_date=day, user=books.owner, narration=kw.pop("narration", "n"),
        lines=[{"account": _acct(books, debit_code), "debit": Decimal(amount), **kw}, {"account": _acct(books, credit_code), "credit": Decimal(amount)}],
    )


def test_lists_every_line_with_voucher_type_and_balances(books):  # noqa: F811
    _post(books, 1, date(2026, 6, 1), "1100", "4100", "500", source_type="SALES_INVOICE")
    _post(books, 2, date(2026, 6, 1), "5000", "1100", "50", source_type="EXPENSE")
    _post(books, 3, date(2026, 6, 1), "5300", "1650", "20", source_type="FIXED_ASSET", purpose="DEPRECIATION-2026-06")
    _post(books, 4, date(2026, 6, 1), "1100", "3100", "5", source_type="MANUAL_JOURNAL")
    data = books.client.get(L, {"date": "2026-06-01"}).data
    assert data["count"] == 8
    types = {r["voucher_type"] for r in data["results"]}
    assert {"SALES", "EXPENSE", "DEPRECIATION", "JOURNAL"} <= types
    assert data["totals"]["balanced"] is True and Decimal(data["totals"]["debit"]) == Decimal("575")
    assert data["tie_out"]["ties"] is True
    assert all(d["balanced"] for d in data["day_totals"])


def test_filters_by_type_account_cost_centre_party_and_text(books):  # noqa: F811
    cc = CostCenter.objects.create(company=books.company, code="S1", name="Shop")
    _post(books, 1, date(2026, 6, 1), "1100", "4100", "500", source_type="SALES_INVOICE", narration="cake sale")
    _post(books, 2, date(2026, 6, 1), "5000", "1100", "50", source_type="EXPENSE", cost_center=cc)
    base = {"date": "2026-06-01"}
    assert books.client.get(L, {**base, "voucher_type": "SALES"}).data["count"] == 2
    assert books.client.get(L, {**base, "account": _acct(books, "5000").id}).data["count"] == 1
    assert books.client.get(L, {**base, "cost_center": cc.id}).data["count"] == 1
    assert books.client.get(L, {**base, "q": "cake"}).data["count"] == 2
    filtered = books.client.get(L, {**base, "voucher_type": "EXPENSE"}).data
    assert Decimal(filtered["totals"]["debit"]) == Decimal("50")
    assert books.client.get(L, {**base, "voucher_type": "NOPE"}).status_code == 400


def test_expense_appears_only_once_posted(books):  # noqa: F811
    cat = ExpenseCategory.objects.create(company=books.company, name="Tea")
    resp = books.client.post("/api/v1/accounting/expenses/", {"category": cat.id, "expense_date": "2026-06-02", "amount": "30"}, format="json")
    assert resp.status_code == 201
    assert books.client.get(L, {"date": "2026-06-02"}).data["count"] == 0  # register only, no start date
    books.company.expense_gl_start_date = date(2026, 1, 1)
    books.company.save(update_fields=["expense_gl_start_date"])
    books.client.post("/api/v1/accounting/expenses/post-pending/", {}, format="json")
    assert books.client.get(L, {"date": "2026-06-02", "voucher_type": "EXPENSE"}).data["count"] == 2
    assert Expense.objects.filter(company=books.company, journal_entry__isnull=False).count() == 1


def test_date_validation_and_range_limit(books):  # noqa: F811
    assert books.client.get(L, {"date": "not-a-date"}).status_code == 400
    assert books.client.get(L, {"date_from": "2026-06-10", "date_to": "2026-06-01"}).status_code == 400
    assert books.client.get(L, {"date_from": "2026-01-01", "date_to": "2026-03-31"}).status_code == 400
    assert books.client.get(C, {"date": "garbage"}).status_code == 400


def test_pagination_and_neighbour_days(books):  # noqa: F811
    for n in range(30):
        _post(books, 100 + n, date(2026, 6, 5), "1100", "4100", "1")
    page1 = books.client.get(L, {"date": "2026-06-05", "page_size": 25}).data
    assert page1["count"] == 60 and len(page1["results"]) == 25
    assert page1["previous"] == "2026-06-04" and page1["next"] == "2026-06-06"
    page3 = books.client.get(L, {"date": "2026-06-05", "page_size": 25, "page": 3}).data
    assert len(page3["results"]) == 10
    assert Decimal(page1["totals"]["debit"]) == Decimal("30")  # totals cover the whole day, not the page


def test_reversed_entries_show_with_their_reversal(books):  # noqa: F811
    entry = _post(books, 1, date(2026, 6, 1), "1100", "4100", "40", source_type="MANUAL_JOURNAL")
    PostingService.reverse(entry, books.owner)
    data = books.client.get(L, {"date": "2026-06-01"}).data
    assert data["count"] == 4 and data["totals"]["balanced"] is True
    assert {r["status"] for r in data["results"]} == {"POSTED", "REVERSED"}
    assert JournalEntry.objects.filter(company=books.company).count() == 2


def test_export_csv_and_xlsx_need_the_export_right(books):  # noqa: F811
    _post(books, 1, date(2026, 6, 1), "1100", "4100", "40")
    csv = books.client.get(L, {"date": "2026-06-01", "file": "csv"})
    assert csv.status_code == 200 and csv.content.decode().splitlines()[0].startswith("Date,Voucher")
    assert books.client.get(L, {"date": "2026-06-01", "file": "xlsx"}).status_code == 200
    assert books.staff_client.get(L, {"date": "2026-06-01", "file": "csv"}).status_code == 403


def test_voucher_type_mapping_helpers():
    assert ledger.voucher_type_of("FIXED_ASSET", "DEPRECIATION-2026-06") == "DEPRECIATION"
    assert ledger.voucher_type_of("FIXED_ASSET", "DISPOSAL") == "FIXED_ASSET"
    assert ledger.voucher_type_of("SOMETHING_NEW", "") == "OTHER"


# ------------------------------------------------------------------ cash summary semantics
def test_cash_summary_keeps_returns_out_of_cash_net(books):  # noqa: F811
    from reporting.transactions import day_book

    summary = day_book(books.company, date(2026, 6, 1))
    assert summary["label"] == "Daily cash summary"
    assert set(summary["adjustments"]) == {"sales_returns", "credit_notes", "debit_notes"}
    assert summary["net"] == summary["inflow"] - summary["outflow"]
