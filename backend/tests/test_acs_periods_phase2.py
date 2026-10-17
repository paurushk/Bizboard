"""ACS-30..34: close readiness, reopen, generate year, FY close preview and reversal."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from accounting.models import Account, AccountingPeriod, JournalEntry
from accounting.services import PostingService
from reporting.models import GstReturnPeriod
from tests.test_sprint_a_accounting_p1 import books  # noqa: F401

pytestmark = pytest.mark.django_db

P = "/api/v1/accounting/periods/"
FY = "/api/v1/accounting/fy-close/"


def _period(books, name, start, end, status=AccountingPeriod.Status.OPEN):  # noqa: F811
    return AccountingPeriod.objects.create(
        company=books.company, name=name, start_date=start, end_date=end, status=status,
    )


def _acct(books, code):  # noqa: F811
    return Account.objects.get(company=books.company, code=code)


# ----------------------------------------------------------------- ACS-30
def test_readiness_lists_earlier_open_period_and_blocks_later_close(books):  # noqa: F811
    _period(books, "Apr 2026", "2026-04-01", "2026-04-30")
    may = _period(books, "May 2026", "2026-05-01", "2026-05-31")
    data = books.client.get(f"{P}{may.id}/close-readiness/").data
    assert data["earlier_open_period"]["name"] == "Apr 2026"
    assert data["can_close"] is False and data["can_soft_close"] is False
    resp = books.client.post(f"{P}{may.id}/close/")
    assert resp.status_code == 400


def test_readiness_ready_month_can_close(books):  # noqa: F811
    apr = _period(books, "Apr 2026", "2026-04-01", "2026-04-30")
    data = books.client.get(f"{P}{apr.id}/close-readiness/").data
    assert data["blockers"] == []
    assert data["can_close"] is True and data["can_soft_close"] is True
    assert data["gst_status"] == "OPEN"


def test_readiness_reports_blocker_with_fix_path_and_message(books):  # noqa: F811
    from accounting.expense_posting import pending_expenses  # noqa: F401
    from accounting.models import Expense
    from masters.models import ExpenseCategory

    books.company.expense_gl_start_date = date(2026, 4, 1)
    books.company.save(update_fields=["expense_gl_start_date"])
    apr = _period(books, "Apr 2026", "2026-04-01", "2026-04-30")
    cat = ExpenseCategory.objects.create(company=books.company, name="Tea")
    Expense.objects.create(
        company=books.company, category=cat, expense_date="2026-04-10", amount=Decimal("50.00"),
        number="EXP-1", created_by=books.owner, updated_by=books.owner,
    )
    data = books.client.get(f"{P}{apr.id}/close-readiness/").data
    codes = {b["code"]: b for b in data["blockers"]}
    assert "EXPENSE_MISSING_POSTING" in codes
    assert codes["EXPENSE_MISSING_POSTING"]["fix_path"] == "/accounting/expenses"
    assert data["can_close"] is False
    refusal = books.client.post(f"{P}{apr.id}/close/")
    assert refusal.status_code == 400
    assert "Expenses are not posted" in str(refusal.data)


def test_summary_computes_readiness_only_for_first_unclosed(books):  # noqa: F811
    _period(books, "Mar 2026", "2026-03-01", "2026-03-31", AccountingPeriod.Status.CLOSED)
    _period(books, "Apr 2026", "2026-04-01", "2026-04-30")
    _period(books, "May 2026", "2026-05-01", "2026-05-31")
    rows = {r["name"]: r for r in books.client.get(P + "close-summary/").data["results"]}
    assert rows["Apr 2026"]["blocker_count"] == 0
    assert rows["May 2026"]["blocker_count"] is None and rows["May 2026"]["blocked_by_earlier"] is True
    assert rows["Mar 2026"]["blocker_count"] is None and rows["Mar 2026"]["blocked_by_earlier"] is False


# ----------------------------------------------------------------- ACS-32
def test_reopen_steps_back_one_level_and_needs_reason(books):  # noqa: F811
    apr = _period(books, "Apr 2026", "2026-04-01", "2026-04-30", AccountingPeriod.Status.CLOSED)
    assert books.client.post(f"{P}{apr.id}/reopen/", {}, format="json").status_code == 400
    r1 = books.client.post(f"{P}{apr.id}/reopen/", {"reason": "late bill"}, format="json")
    assert r1.status_code == 200 and r1.data["status"] == "SOFT_CLOSED"
    r2 = books.client.post(f"{P}{apr.id}/reopen/", {"reason": "late bill"}, format="json")
    assert r2.status_code == 200 and r2.data["status"] == "OPEN"
    assert books.client.post(f"{P}{apr.id}/reopen/", {"reason": "x"}, format="json").status_code == 400


def test_reopen_is_owner_only(books):  # noqa: F811
    apr = _period(books, "Apr 2026", "2026-04-01", "2026-04-30", AccountingPeriod.Status.CLOSED)
    assert books.staff_client.post(f"{P}{apr.id}/reopen/", {"reason": "x"}, format="json").status_code == 403
    apr.refresh_from_db()
    assert apr.status == AccountingPeriod.Status.CLOSED


def test_reopen_refused_when_later_month_closed(books):  # noqa: F811
    apr = _period(books, "Apr 2026", "2026-04-01", "2026-04-30", AccountingPeriod.Status.CLOSED)
    _period(books, "May 2026", "2026-05-01", "2026-05-31", AccountingPeriod.Status.CLOSED)
    resp = books.client.post(f"{P}{apr.id}/reopen/", {"reason": "x"}, format="json")
    assert resp.status_code == 400 and "May 2026" in str(resp.data)


def test_reopen_refused_when_gst_month_closed(books):  # noqa: F811
    apr = _period(books, "Apr 2026", "2026-04-01", "2026-04-30", AccountingPeriod.Status.CLOSED)
    GstReturnPeriod.objects.create(company=books.company, period="2026-04", status=GstReturnPeriod.Status.CLOSED)
    resp = books.client.post(f"{P}{apr.id}/reopen/", {"reason": "x"}, format="json")
    assert resp.status_code == 400 and "GST" in str(resp.data)


# ----------------------------------------------------------------- ACS-33
def test_generate_year_creates_twelve_months_and_is_idempotent(books):  # noqa: F811
    first = books.client.post(P + "generate/", {"fy_start_year": 2026}, format="json")
    assert first.status_code == 201
    assert len(first.data["created"]) == 12 and first.data["skipped"] == []
    names = list(AccountingPeriod.objects.filter(company=books.company).order_by("start_date").values_list("name", flat=True))
    assert names[0] == "Apr 2026" and names[-1] == "Mar 2027"
    second = books.client.post(P + "generate/", {"fy_start_year": 2026}, format="json")
    assert second.status_code == 201
    assert second.data["created"] == [] and len(second.data["skipped"]) == 12
    assert AccountingPeriod.objects.filter(company=books.company).count() == 12


def test_generate_year_refuses_overlap_and_creates_nothing(books):  # noqa: F811
    _period(books, "Odd", "2026-06-10", "2026-07-10")
    resp = books.client.post(P + "generate/", {"fy_start_year": 2026}, format="json")
    assert resp.status_code == 400
    assert AccountingPeriod.objects.filter(company=books.company).count() == 1


# ----------------------------------------------------------------- ACS-34
def _book_profit(books):  # noqa: F811
    PostingService.post(
        company=books.company, source_type="TEST", source_id=1, purpose="SALE", entry_date=date(2026, 6, 10),
        user=books.owner, narration="sale",
        lines=[{"account": _acct(books, "1100"), "debit": Decimal("1000")}, {"account": _acct(books, "4100"), "credit": Decimal("1000")}],
    )
    PostingService.post(
        company=books.company, source_type="TEST", source_id=2, purpose="COST", entry_date=date(2026, 6, 11),
        user=books.owner, narration="cost",
        lines=[{"account": _acct(books, "5400"), "debit": Decimal("400")}, {"account": _acct(books, "1100"), "credit": Decimal("400")}],
    )


def test_fy_close_preview_shows_totals_without_closing(books):  # noqa: F811
    _book_profit(books)
    books.client.post(P + "generate/", {"fy_start_year": 2026}, format="json")
    data = books.client.get(FY, {"fy_end": "2027-03-31"}).data
    assert data["income"] == "1000.00" or Decimal(data["income"]) == Decimal("1000")
    assert Decimal(data["expense"]) == Decimal("400")
    assert Decimal(data["net_profit"]) == Decimal("600")
    assert data["already_closed"] is False
    assert JournalEntry.objects.filter(company=books.company, source_type="FY_CLOSE").count() == 0


def test_fy_close_then_reverse_restores_profit_and_reopens_months(books):  # noqa: F811
    _book_profit(books)
    books.client.post(P + "generate/", {"fy_start_year": 2026}, format="json")
    closed = books.client.post(FY, {"fy_end": "2027-03-31", "confirm": True}, format="json")
    assert closed.status_code == 200, closed.data
    assert AccountingPeriod.objects.filter(company=books.company, status="CLOSED").count() == 12
    # A month inside a closed year cannot be reopened alone.
    apr = AccountingPeriod.objects.get(company=books.company, name="Jun 2026")
    assert books.client.post(f"{P}{apr.id}/reopen/", {"reason": "x"}, format="json").status_code == 400

    assert books.client.post(FY, {"fy_end": "2027-03-31", "reverse": True}, format="json").status_code == 400  # no reason
    rev = books.client.post(FY, {"fy_end": "2027-03-31", "reverse": True, "reason": "wrong year"}, format="json")
    assert rev.status_code == 200, rev.data
    assert AccountingPeriod.objects.filter(company=books.company, status="SOFT_CLOSED").count() == 12
    original = JournalEntry.objects.get(pk=closed.data["journal_id"])
    assert original.status == JournalEntry.Status.REVERSED

    pnl = books.client.get("/api/v1/accounting/profit-and-loss/", {"date_from": "2026-04-01", "date_to": "2027-03-31"}).data
    assert Decimal(str(pnl.get("income") or pnl.get("totalIncome") or pnl.get("total_income") or 0)) == Decimal("1000")

    again = books.client.post(FY, {"fy_end": "2027-03-31", "confirm": True}, format="json")
    assert again.status_code == 200, again.data


def test_reverse_fy_close_requires_a_closed_year_and_owner(books):  # noqa: F811
    resp = books.client.post(FY, {"fy_end": "2027-03-31", "reverse": True, "reason": "x"}, format="json")
    assert resp.status_code == 400
    assert books.staff_client.post(FY, {"fy_end": "2027-03-31", "reverse": True, "reason": "x"}, format="json").status_code == 403
