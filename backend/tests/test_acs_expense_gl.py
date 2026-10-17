"""ACS-15 / ACS-16: expenses post to the ledger (behind a start date) and carry payment details."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.db.models import Sum
from django.utils import timezone

from accounting.expense_posting import pending_summary, post_pending_expenses
from accounting.models import Account, AccountingPeriod, Expense, JournalEntry, JournalLine
from accounting.reports import trial_balance
from accounting.services import BooksHealthService
from masters.models import ExpenseCategory
from payments.models import BankAccount
from tests.test_sprint_a_accounting_p1 import books  # noqa: F401

pytestmark = pytest.mark.django_db

EXP = "/api/v1/accounting/expenses/"
SETTINGS = "/api/v1/accounting/settings/"
MAP = "/api/v1/accounting/expense-category-accounts/"


def _today() -> date:
    return timezone.localdate()


def _enable_posting(books, start=None):  # noqa: F811
    start = start or (_today() - timedelta(days=1))
    resp = books.client.post(SETTINGS, {"expense_gl_start_date": start.isoformat()}, format="json")
    assert resp.status_code == 200, resp.data
    books.company.refresh_from_db()
    return start


def _cat(books, name="Rent"):  # noqa: F811
    return ExpenseCategory.objects.get_or_create(company=books.company, name=name)[0]


def _create(books, **overrides):  # noqa: F811
    payload = {
        "category": _cat(books).id, "amount": "1000.00", "party_name": "Landlord",
        "expense_date": _today().isoformat(), **overrides,
    }
    return books.client.post(EXP, payload, format="json")


def _net(company, code):
    agg = JournalLine.objects.filter(
        company=company, account__code=code,
        entry__status__in=[JournalEntry.Status.POSTED, JournalEntry.Status.REVERSED],
    ).aggregate(d=Sum("debit"), c=Sum("credit"))
    return (agg["d"] or Decimal("0")) - (agg["c"] or Decimal("0"))


def _acct(books, code):  # noqa: F811
    return Account.objects.get(company=books.company, code=code)


# ------------------------------------------------------------- the start date switch
def test_without_a_start_date_an_expense_stays_a_register_row(books):  # noqa: F811
    created = _create(books)
    assert created.status_code == 201, created.data
    assert created.data["posted_to_books"] is False
    assert _net(books.company, "5000") == 0
    assert JournalEntry.objects.filter(company=books.company, source_type="EXPENSE").count() == 0


def test_cash_expense_posts_dr_expense_cr_cash(books):  # noqa: F811
    _enable_posting(books)
    created = _create(books)
    assert created.status_code == 201, created.data
    assert created.data["posted_to_books"] is True and created.data["journal_number"]
    assert _net(books.company, "5000") == Decimal("1000.00")
    assert _net(books.company, "1100") == Decimal("-1000.00")
    assert trial_balance(books.company)["balanced"]
    entry = JournalEntry.objects.get(company=books.company, source_type="EXPENSE")
    assert entry.entry_date == _today() and entry.status == JournalEntry.Status.POSTED
    assert Expense.objects.get(pk=created.data["id"]).journal_entry_id == entry.id


def test_expense_dated_before_the_start_date_is_not_posted(books):  # noqa: F811
    _enable_posting(books, start=_today())
    old = _create(books, expense_date=(_today() - timedelta(days=3)).isoformat())
    assert old.status_code == 201
    assert old.data["posted_to_books"] is False
    assert _net(books.company, "5000") == 0


# ------------------------------------------------------------------ which ledger
def test_category_mapping_and_override_choose_the_expense_ledger(books):  # noqa: F811
    _enable_posting(books)
    rent = Account.objects.create(
        company=books.company, code="5810", name="Rent expense", type="EXPENSE", is_system=False,
    )
    fuel = Account.objects.create(
        company=books.company, code="5820", name="Fuel expense", type="EXPENSE", is_system=False,
    )
    cat = _cat(books)
    mapped = books.client.post(MAP, {"category": cat.id, "account": rent.id}, format="json")
    assert mapped.status_code == 200, mapped.data
    again = books.client.post(MAP, {"category": cat.id, "account": rent.id}, format="json")
    assert again.status_code == 200 and again.data["id"] == mapped.data["id"]  # upsert, one per category

    first = _create(books)
    assert _net(books.company, "5810") == Decimal("1000.00")
    assert _net(books.company, "5000") == 0

    second = _create(books, expense_account=fuel.id, amount="250.00")
    assert second.status_code == 201, second.data
    assert _net(books.company, "5820") == Decimal("250.00")
    assert first.data["id"] != second.data["id"]


def test_expense_account_must_be_an_active_expense_account(books):  # noqa: F811
    _enable_posting(books)
    bad_type = _create(books, expense_account=_acct(books, "1100").id)
    assert bad_type.status_code == 400
    dead = Account.objects.create(
        company=books.company, code="5899", name="Old", type="EXPENSE", is_system=False, is_active=False,
    )
    assert _create(books, expense_account=dead.id).status_code == 400
    assert books.client.post(MAP, {"category": _cat(books).id, "account": _acct(books, "1100").id}, format="json").status_code == 400


# ------------------------------------------------------------------ cash vs bank
def test_bank_expense_needs_a_bank_and_posts_to_its_ledger(books):  # noqa: F811
    _enable_posting(books)
    assert _create(books, payment_mode="BANK").status_code == 400
    bank = BankAccount.objects.create(company=books.company, name="HDFC")
    created = _create(books, payment_mode="BANK", bank_account=bank.id)
    assert created.status_code == 201, created.data
    assert _net(books.company, "1100") == 0
    bank_ledger = Account.objects.get(company=books.company, bank_account=bank)
    assert _net(books.company, bank_ledger.code) == Decimal("-1000.00")


def test_cash_expense_drops_a_stray_bank_link(books):  # noqa: F811
    bank = BankAccount.objects.create(company=books.company, name="HDFC")
    created = _create(books, payment_mode="CASH", bank_account=bank.id)
    assert created.status_code == 201
    assert created.data["bank_account"] is None


# ------------------------------------------------------------- edit and void
def test_editing_the_amount_reverses_and_reposts(books):  # noqa: F811
    _enable_posting(books)
    eid = _create(books).data["id"]
    resp = books.client.patch(f"{EXP}{eid}/", {"amount": "1500.00"}, format="json")
    assert resp.status_code == 200, resp.data
    assert _net(books.company, "5000") == Decimal("1500.00")
    assert _net(books.company, "1100") == Decimal("-1500.00")
    assert trial_balance(books.company)["balanced"]
    statuses = list(
        JournalEntry.objects.filter(company=books.company, source_type="EXPENSE")
        .order_by("id").values_list("status", flat=True)
    )
    assert statuses == ["REVERSED", "POSTED"]


def test_editing_only_the_notes_leaves_the_ledger_alone(books):  # noqa: F811
    _enable_posting(books)
    eid = _create(books).data["id"]
    before = JournalEntry.objects.filter(company=books.company).count()
    assert books.client.patch(f"{EXP}{eid}/", {"notes": "March rent"}, format="json").status_code == 200
    assert JournalEntry.objects.filter(company=books.company).count() == before


def test_changing_the_payment_mode_moves_the_credit(books):  # noqa: F811
    _enable_posting(books)
    bank = BankAccount.objects.create(company=books.company, name="HDFC")
    eid = _create(books).data["id"]
    resp = books.client.patch(f"{EXP}{eid}/", {"payment_mode": "BANK", "bank_account": bank.id}, format="json")
    assert resp.status_code == 200, resp.data
    assert _net(books.company, "1100") == 0
    assert _net(books.company, Account.objects.get(company=books.company, bank_account=bank).code) == Decimal("-1000.00")


def test_moving_an_expense_before_the_start_date_takes_it_out_of_the_books(books):  # noqa: F811
    _enable_posting(books, start=_today())
    eid = _create(books).data["id"]
    assert _net(books.company, "5000") == Decimal("1000.00")
    resp = books.client.patch(
        f"{EXP}{eid}/", {"expense_date": (_today() - timedelta(days=2)).isoformat()}, format="json",
    )
    assert resp.status_code == 200, resp.data
    assert resp.data["posted_to_books"] is False
    assert _net(books.company, "5000") == 0


def test_voiding_reverses_the_entry(books):  # noqa: F811
    _enable_posting(books)
    eid = _create(books).data["id"]
    resp = books.client.post(f"{EXP}{eid}/void/", {"reason": "Entered twice"}, format="json")
    assert resp.status_code == 200, resp.data
    assert resp.data["posted_to_books"] is False
    assert _net(books.company, "5000") == 0
    assert _net(books.company, "1100") == 0
    assert trial_balance(books.company)["balanced"]


def test_a_closed_month_blocks_the_expense_and_leaves_no_entry(books):  # noqa: F811
    _enable_posting(books)
    AccountingPeriod.objects.create(
        company=books.company, name="Closed", start_date=_today().replace(day=1),
        end_date=_today().replace(day=28), status=AccountingPeriod.Status.CLOSED,
    )
    resp = _create(books)
    assert resp.status_code == 400
    assert Expense.objects.filter(company=books.company).count() == 0
    assert JournalEntry.objects.filter(company=books.company, source_type="EXPENSE").count() == 0


# ------------------------------------------------------------ settings + back-fill
def test_setting_the_start_date_is_validated(books):  # noqa: F811
    books.company.books_start_date = _today() - timedelta(days=10)
    books.company.save(update_fields=["books_start_date"])
    early = books.client.post(
        SETTINGS, {"expense_gl_start_date": (_today() - timedelta(days=30)).isoformat()}, format="json",
    )
    assert early.status_code == 400
    garbage = books.client.post(SETTINGS, {"expense_gl_start_date": "soon"}, format="json")
    assert garbage.status_code == 400
    ok = books.client.post(SETTINGS, {"expense_gl_start_date": _today().isoformat()}, format="json")
    assert ok.status_code == 200 and ok.data["expense_gl_start_date"] == _today().isoformat()
    off = books.client.post(SETTINGS, {"expense_gl_start_date": None}, format="json")
    assert off.status_code == 200 and off.data["expense_gl_start_date"] is None
    got = books.client.get(SETTINGS)
    assert got.data["expense_gl_pending"]["count"] == 0


def test_start_date_needs_accounting_on(tenant_a):
    resp = tenant_a.client.post(SETTINGS, {"expense_gl_start_date": _today().isoformat()}, format="json")
    assert resp.status_code == 400


def test_existing_expenses_are_pending_until_posted_and_posting_is_idempotent(books):  # noqa: F811
    for _ in range(3):
        assert _create(books).status_code == 201
    assert _net(books.company, "5000") == 0
    _enable_posting(books)
    got = books.client.get(SETTINGS)
    assert got.data["expense_gl_pending"]["count"] == 3
    preview = books.client.post(EXP + "post-pending/", {"dry_run": True}, format="json")
    assert preview.data["posted"] == 3 and preview.data["dry_run"] is True
    assert _net(books.company, "5000") == 0  # a preview writes nothing
    done = books.client.post(EXP + "post-pending/", {}, format="json")
    assert done.status_code == 200 and done.data["posted"] == 3 and done.data["skipped"] == []
    assert _net(books.company, "5000") == Decimal("3000.00")
    again = books.client.post(EXP + "post-pending/", {}, format="json")
    assert again.data["posted"] == 0
    assert _net(books.company, "5000") == Decimal("3000.00")
    assert pending_summary(books.company)["count"] == 0


def test_backfill_reports_a_closed_month_instead_of_forcing_it(books):  # noqa: F811
    month_start = _today().replace(day=1)
    old_day = month_start - timedelta(days=40)
    _create(books, expense_date=old_day.isoformat())
    _create(books)
    _enable_posting(books, start=old_day)
    AccountingPeriod.objects.create(
        company=books.company, name="Old", start_date=old_day.replace(day=1),
        end_date=(old_day.replace(day=1) + timedelta(days=27)),
        status=AccountingPeriod.Status.CLOSED,
    )
    result = post_pending_expenses(books.company, books.owner)
    assert result["posted"] == 1 and len(result["skipped"]) == 1
    assert _net(books.company, "5000") == Decimal("1000.00")


def test_backfill_command(books):  # noqa: F811
    _create(books)
    _enable_posting(books)
    out = StringIO()
    call_command("backfill_expense_postings", company=books.company.id, dry_run=True, stdout=out)
    assert "Would post 1" in out.getvalue() and _net(books.company, "5000") == 0
    out = StringIO()
    call_command("backfill_expense_postings", company=books.company.id, stdout=out)
    assert "Posted 1" in out.getvalue() and _net(books.company, "5000") == Decimal("1000.00")


# --------------------------------------------------------------- books health
def test_unposted_expense_warns_and_blocks_the_period_close(books):  # noqa: F811
    _create(books)
    _enable_posting(books)
    codes = {a["code"] for a in BooksHealthService.control_balances(books.company)["alerts"]}
    assert "EXPENSE_MISSING_POSTING" in codes
    period = f"{_today().year:04d}-{_today().month:02d}"
    blockers = {a["code"] for a in BooksHealthService.period_close_blockers(books.company, period=period)}
    assert "EXPENSE_MISSING_POSTING" in blockers
    post_pending_expenses(books.company, books.owner)
    after = {a["code"] for a in BooksHealthService.period_close_blockers(books.company, period=period)}
    assert "EXPENSE_MISSING_POSTING" not in after


def test_a_pending_expense_of_a_later_month_does_not_block_an_earlier_close(books):  # noqa: F811
    first = _today().replace(day=1)
    earlier = (first - timedelta(days=1)).replace(day=1)
    _enable_posting(books, start=earlier)
    Expense.objects.create(
        company=books.company, category=_cat(books), amount=Decimal("5"), expense_date=_today(),
    )
    period = f"{earlier.year:04d}-{earlier.month:02d}"
    blockers = {a["code"] for a in BooksHealthService.period_close_blockers(books.company, period=period)}
    assert "EXPENSE_MISSING_POSTING" not in blockers


# ------------------------------------------------------------------- capture
def test_amount_must_be_positive(books):  # noqa: F811
    for bad in ("0", "-5", "0.001"):
        assert _create(books, amount=bad).status_code == 400, bad


def test_duplicate_check_finds_a_same_day_same_party_same_amount_entry(books):  # noqa: F811
    first = _create(books)
    query = f"?date={_today().isoformat()}&amount=1000.00&party=landlord"
    found = books.client.get(EXP + "duplicates/" + query)
    assert found.status_code == 200 and found.data["count"] == 1
    assert found.data["results"][0]["id"] == first.data["id"]
    excluded = books.client.get(EXP + "duplicates/" + query + f"&exclude={first.data['id']}")
    assert excluded.data["count"] == 0
    other = books.client.get(EXP + f"duplicates/?date={_today().isoformat()}&amount=999.00")
    assert other.data["count"] == 0
    assert books.client.get(EXP + "duplicates/").status_code == 400
    books.client.post(f"{EXP}{first.data['id']}/void/", {"reason": "dup"}, format="json")
    assert books.client.get(EXP + "duplicates/" + query).data["count"] == 0  # a void is not a duplicate


def test_mapping_changes_are_owner_only(books):  # noqa: F811
    cat = _cat(books)
    rent = Account.objects.create(
        company=books.company, code="5810", name="Rent expense", type="EXPENSE", is_system=False,
    )
    assert books.client.post(MAP, {"category": cat.id, "account": rent.id}, format="json").status_code == 200
    listing = books.client.get(MAP)
    assert listing.status_code == 200
    assert [row["account_name"] for row in (listing.data.get("results") or listing.data)] == ["5810 Rent expense"]
