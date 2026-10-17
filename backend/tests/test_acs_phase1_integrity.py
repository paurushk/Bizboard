"""ACS-01 / ACS-10..14: Accounting-screen integrity guards.

Plan: ACCOUNTING_SCREENS_IMPLEMENTATION_PLAN.md (Phase 1). Review findings R2, R3, R4, R6, R9.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from accounting.models import Account, AccountingPeriod, Expense, FixedAsset, JournalEntry
from accounting.services import PostingService
from core.exceptions import BusinessRuleError
from reporting.gst_periods import soft_close_period
from tests.conftest import make_customer
from tests.test_sprint_a_accounting_p1 import _completed_invoice, books  # noqa: F401

pytestmark = pytest.mark.django_db

J = "/api/v1/accounting/journals/"
FA = "/api/v1/accounting/fixed-assets/"
EXP = "/api/v1/accounting/expenses/"


def _acct(company, code):
    return Account.objects.get(company=company, code=code)


def _manual_posted(books, *, entry_date=None):  # noqa: F811
    cash, cogs = _acct(books.company, "1100"), _acct(books.company, "5400")
    created = books.client.post(
        J,
        {
            "entry_date": (entry_date or timezone.localdate()).isoformat(),
            "narration": "manual",
            "lines": [
                {"account": cogs.id, "debit": "100.00", "credit": "0"},
                {"account": cash.id, "debit": "0", "credit": "100.00"},
            ],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    jid = created.data["id"]
    posted = books.client.post(f"{J}{jid}/post/")
    assert posted.status_code == 200, posted.data
    return jid


# --------------------------------------------------------------------- ACS-01
def test_manual_journal_unbalanced_rejected_and_balanced_posts(books):  # noqa: F811
    cash, cogs = _acct(books.company, "1100"), _acct(books.company, "5400")
    bad = books.client.post(
        J,
        {"entry_date": "2026-06-10", "lines": [
            {"account": cogs.id, "debit": "100", "credit": "0"},
            {"account": cash.id, "debit": "0", "credit": "90"},
        ]},
        format="json",
    )
    assert bad.status_code == 400
    jid = _manual_posted(books)
    assert JournalEntry.objects.get(pk=jid).status == JournalEntry.Status.POSTED


def test_manual_journal_period_guards_stay(books):  # noqa: F811
    today = timezone.localdate()
    soft_close_period(books.company, f"{today.year:04d}-{today.month:02d}", books.owner)
    cash, cogs = _acct(books.company, "1100"), _acct(books.company, "5400")
    created = books.client.post(
        J,
        {"entry_date": today.isoformat(), "lines": [
            {"account": cogs.id, "debit": "10", "credit": "0"},
            {"account": cash.id, "debit": "0", "credit": "10"},
        ]},
        format="json",
    )
    assert created.status_code == 201
    posted = books.client.post(f"{J}{created.data['id']}/post/")
    assert posted.status_code == 400


# --------------------------------------------------------------------- ACS-10
def test_manual_journal_reverses_and_exposes_source_fields(books):  # noqa: F811
    jid = _manual_posted(books)
    detail = books.client.get(f"{J}{jid}/")
    assert detail.data["source_type"] == "MANUAL_JOURNAL"
    assert detail.data["can_reverse"] is True
    rev = books.client.post(f"{J}{jid}/reverse/")
    assert rev.status_code == 200, rev.data
    assert JournalEntry.objects.get(pk=jid).status == JournalEntry.Status.REVERSED
    # the reversal itself is a system entry and cannot be reversed again
    reversal_id = JournalEntry.objects.get(pk=jid).reversed_entry_id
    again = books.client.post(f"{J}{reversal_id}/reverse/")
    assert again.status_code == 400
    assert "journal_system_not_reversible" in str(again.data) or "reversal" in str(again.data).lower()


def test_system_journal_cannot_be_reversed_from_the_journals_screen(books):  # noqa: F811
    customer = make_customer(books.company)
    invoice = _completed_invoice(books.company, customer)
    entry = PostingService.post_sales_invoice(invoice, books.owner)
    detail = books.client.get(f"{J}{entry.id}/")
    assert detail.data["can_reverse"] is False
    assert detail.data["source_path"] == f"/sales/history/{invoice.id}"
    assert "sales invoice" in detail.data["source_label"]
    resp = books.client.post(f"{J}{entry.id}/reverse/")
    assert resp.status_code == 400, resp.data
    assert "sales invoice" in str(resp.data).lower()
    entry.refresh_from_db()
    assert entry.status == JournalEntry.Status.POSTED


def test_system_journal_not_reversible_even_in_a_soft_closed_month(books):  # noqa: F811
    customer = make_customer(books.company)
    invoice = _completed_invoice(books.company, customer, invoice_date=timezone.localdate().isoformat())
    entry = PostingService.post_sales_invoice(invoice, books.owner)
    today = timezone.localdate()
    soft_close_period(books.company, f"{today.year:04d}-{today.month:02d}", books.owner)
    resp = books.client.post(f"{J}{entry.id}/reverse/")
    assert resp.status_code == 400


def test_manual_reverse_in_soft_closed_month_still_refused(books):  # noqa: F811
    jid = _manual_posted(books)
    today = timezone.localdate()
    soft_close_period(books.company, f"{today.year:04d}-{today.month:02d}", books.owner)
    resp = books.client.post(f"{J}{jid}/reverse/")
    assert resp.status_code == 400


# --------------------------------------------------------------------- ACS-11
def test_inactive_account_refused_in_manual_journal(books):  # noqa: F811
    cash, cogs = _acct(books.company, "1100"), _acct(books.company, "5400")
    cogs.is_active = False
    cogs.save(update_fields=["is_active"])
    resp = books.client.post(
        J,
        {"entry_date": "2026-06-10", "lines": [
            {"account": cogs.id, "debit": "10", "credit": "0"},
            {"account": cash.id, "debit": "0", "credit": "10"},
        ]},
        format="json",
    )
    assert resp.status_code == 400
    assert "inactive" in str(resp.data).lower()


def test_posting_service_refuses_inactive_account_but_reverse_unwinds(books):  # noqa: F811
    cash, cogs = _acct(books.company, "1100"), _acct(books.company, "5400")
    entry = PostingService.post(
        company=books.company, source_type="TEST", source_id=1, purpose="A",
        entry_date=date(2026, 6, 10), user=books.owner,
        lines=[{"account": cogs, "debit": 25}, {"account": cash, "credit": 25}],
    )
    cogs.is_active = False
    cogs.save(update_fields=["is_active"])
    with pytest.raises(BusinessRuleError, match="inactive"):
        PostingService.post(
            company=books.company, source_type="TEST", source_id=2, purpose="B",
            entry_date=date(2026, 6, 11), user=books.owner,
            lines=[{"account": cogs, "debit": 5}, {"account": cash, "credit": 5}],
        )
    reversal = PostingService.reverse(entry, books.owner)
    assert reversal.status == JournalEntry.Status.POSTED


# ------------------------------------------------------------- ACS-12 / ACS-13
@pytest.fixture
def assets(books, settings):  # noqa: F811
    settings.ENABLE_FIXED_ASSETS = True
    return books


def _asset(assets, **overrides):
    payload = {
        "name": "Laptop", "acquisition_cost": "120000.00", "acquisition_date": "2026-01-15",
        "useful_life_months": 36,
    }
    payload.update(overrides)
    resp = assets.client.post(FA, payload, format="json")
    assert resp.status_code == 201, resp.data
    return resp.data["id"]


def _gl(company, code):
    from django.db.models import Sum

    from accounting.models import JournalLine

    agg = JournalLine.objects.filter(
        company=company, account__code=code, entry__status=JournalEntry.Status.POSTED,
    ).aggregate(d=Sum("debit"), c=Sum("credit"))
    return (agg["d"] or Decimal("0")) - (agg["c"] or Decimal("0"))


def test_dispose_with_proceeds_books_gain_and_cash(assets):
    aid = _asset(assets)
    FixedAsset.objects.filter(pk=aid).update(depreciated_amount=Decimal("40000.00"))
    # NBV 80,000; sold for 90,000 -> gain 10,000
    resp = assets.client.post(
        f"{FA}{aid}/dispose/",
        {"confirm": True, "proceeds": "90000", "disposal_date": "2026-06-01"},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    assert _gl(assets.company, "1100") == Decimal("90000.00")
    assert _gl(assets.company, "5700") == Decimal("-10000.00")  # credit = gain
    assert _gl(assets.company, "5600") == Decimal("0")
    asset = FixedAsset.objects.get(pk=aid)
    assert asset.status == FixedAsset.Status.DISPOSED and asset.disposed_at == date(2026, 6, 1)
    entry = JournalEntry.objects.get(source_type="FIXED_ASSET", source_id=aid, purpose="DISPOSAL")
    assert entry.entry_date == date(2026, 6, 1)


def test_dispose_below_book_value_books_loss(assets):
    aid = _asset(assets)
    FixedAsset.objects.filter(pk=aid).update(depreciated_amount=Decimal("40000.00"))
    resp = assets.client.post(
        f"{FA}{aid}/dispose/", {"confirm": True, "proceeds": "50000"}, format="json",
    )
    assert resp.status_code == 200, resp.data
    assert _gl(assets.company, "5600") == Decimal("30000.00")


def test_dispose_to_a_bank_account_uses_its_ledger(assets):
    from payments.models import BankAccount

    bank = BankAccount.objects.create(company=assets.company, name="HDFC")
    aid = _asset(assets)
    resp = assets.client.post(
        f"{FA}{aid}/dispose/",
        {"confirm": True, "proceeds": "1000", "bank_account": bank.id},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    assert _gl(assets.company, "1100") == Decimal("0")
    assert Account.objects.get(company=assets.company, bank_account=bank).code.startswith("1500-")


def test_dispose_date_rules(assets):
    aid = _asset(assets)
    before = assets.client.post(
        f"{FA}{aid}/dispose/", {"confirm": True, "disposal_date": "2025-12-31"}, format="json",
    )
    assert before.status_code == 400
    future = assets.client.post(
        f"{FA}{aid}/dispose/",
        {"confirm": True, "disposal_date": (timezone.localdate() + timedelta(days=5)).isoformat()},
        format="json",
    )
    assert future.status_code == 400
    garbage = assets.client.post(
        f"{FA}{aid}/dispose/", {"confirm": True, "disposal_date": "not-a-date"}, format="json",
    )
    assert garbage.status_code == 400
    assert FixedAsset.objects.get(pk=aid).status == FixedAsset.Status.ACTIVE


def test_dispose_into_a_closed_period_is_refused_and_twice_is_refused(assets):
    aid = _asset(assets)
    AccountingPeriod.objects.create(
        company=assets.company, name="Mar 2026", start_date="2026-03-01", end_date="2026-03-31",
        status=AccountingPeriod.Status.CLOSED,
    )
    closed = assets.client.post(
        f"{FA}{aid}/dispose/", {"confirm": True, "disposal_date": "2026-03-10"}, format="json",
    )
    assert closed.status_code == 400
    ok = assets.client.post(f"{FA}{aid}/dispose/", {"confirm": True}, format="json")
    assert ok.status_code == 200, ok.data
    twice = assets.client.post(f"{FA}{aid}/dispose/", {"confirm": True}, format="json")
    assert twice.status_code == 400


def test_dispose_requires_confirm_and_non_negative_proceeds(assets):
    aid = _asset(assets)
    assert assets.client.post(f"{FA}{aid}/dispose/", {}, format="json").status_code == 400
    assert assets.client.post(
        f"{FA}{aid}/dispose/", {"confirm": True, "proceeds": "-5"}, format="json",
    ).status_code == 400


def test_asset_validation_rules(assets):
    for bad in (
        {"acquisition_cost": "0"},
        {"useful_life_months": 0},
        {"salvage_value": "120000.00"},
        {"wdv_annual_rate": "150"},
    ):
        payload = {
            "name": "X", "acquisition_cost": "1000", "acquisition_date": "2026-01-01",
            "useful_life_months": 12, **bad,
        }
        assert assets.client.post(FA, payload, format="json").status_code == 400, bad


def test_schedule_fields_are_frozen_after_depreciation_but_name_is_editable(assets):
    aid = _asset(assets)
    free = assets.client.patch(f"{FA}{aid}/", {"acquisition_cost": "130000.00"}, format="json")
    assert free.status_code == 200, free.data  # nothing depreciated yet
    FixedAsset.objects.filter(pk=aid).update(depreciated_amount=Decimal("1000.00"))
    for field, value in (
        ("acquisition_cost", "99999.00"),
        ("useful_life_months", 12),
        ("acquisition_date", "2026-02-01"),
        ("salvage_value", "10.00"),
        ("method", "WDV"),
    ):
        resp = assets.client.patch(f"{FA}{aid}/", {field: value}, format="json")
        assert resp.status_code == 400, (field, resp.data)
    ok = assets.client.patch(f"{FA}{aid}/", {"name": "Laptop (renamed)"}, format="json")
    assert ok.status_code == 200, ok.data
    # re-sending the unchanged value is not a change
    same = assets.client.patch(f"{FA}{aid}/", {"useful_life_months": 36}, format="json")
    assert same.status_code == 200, same.data


def test_disposed_asset_cannot_be_edited(assets):
    aid = _asset(assets)
    assert assets.client.post(f"{FA}{aid}/dispose/", {"confirm": True}, format="json").status_code == 200
    assert assets.client.patch(f"{FA}{aid}/", {"name": "nope"}, format="json").status_code == 400


def test_system_owned_asset_fields_are_read_only(assets):
    aid = _asset(assets)
    resp = assets.client.patch(
        f"{FA}{aid}/",
        {"last_depreciation_error": "hacked", "depreciation_catchup_months": "2026-01", "depreciated_amount": "5"},
        format="json",
    )
    assert resp.status_code == 200
    asset = FixedAsset.objects.get(pk=aid)
    assert asset.last_depreciation_error == "" and asset.depreciation_catchup_months == ""
    assert asset.depreciated_amount == 0


# --------------------------------------------------------------------- ACS-14
@pytest.fixture
def expense_cat(tenant_a):
    from masters.models import ExpenseCategory

    return ExpenseCategory.objects.create(company=tenant_a.company, name="Rent")


def _expense(tenant_a, cat, **overrides):
    payload = {"category": cat.id, "amount": "500.00", "party_name": "Landlord", **overrides}
    return tenant_a.client.post(EXP, payload, format="json")


def test_expense_create_edit_blocked_in_closed_period(tenant_a, expense_cat):
    AccountingPeriod.objects.create(
        company=tenant_a.company, name="Mar 2026", start_date="2026-03-01", end_date="2026-03-31",
        status=AccountingPeriod.Status.CLOSED,
    )
    blocked = _expense(tenant_a, expense_cat, expense_date="2026-03-10")
    assert blocked.status_code == 400, blocked.data
    ok = _expense(tenant_a, expense_cat, expense_date="2026-04-10")
    assert ok.status_code == 201, ok.data


def test_expense_cannot_be_moved_into_or_out_of_a_closed_period(tenant_a, expense_cat):
    created = _expense(tenant_a, expense_cat, expense_date="2026-04-10")
    assert created.status_code == 201
    AccountingPeriod.objects.create(
        company=tenant_a.company, name="Mar 2026", start_date="2026-03-01", end_date="2026-03-31",
        status=AccountingPeriod.Status.CLOSED,
    )
    into = tenant_a.client.patch(f"{EXP}{created.data['id']}/", {"expense_date": "2026-03-20"}, format="json")
    assert into.status_code == 400
    # a row already sitting in a month that later closed is frozen as well
    old = Expense.objects.create(
        company=tenant_a.company, category=expense_cat, amount=Decimal("10"),
        expense_date=date(2026, 3, 5), number="EXP-OLD",
    )
    edit = tenant_a.client.patch(f"{EXP}{old.id}/", {"notes": "x"}, format="json")
    assert edit.status_code == 400
    void = tenant_a.client.post(f"{EXP}{old.id}/void/", {"reason": "dup"}, format="json")
    assert void.status_code == 400
    assert Expense.objects.get(pk=old.pk).status == Expense.Status.ACTIVE


def test_expense_void_requires_reason_hides_row_and_keeps_number(tenant_a, expense_cat):
    created = _expense(tenant_a, expense_cat)
    eid, number = created.data["id"], created.data["number"]
    assert tenant_a.client.post(f"{EXP}{eid}/void/", {}, format="json").status_code == 400
    assert tenant_a.client.post(f"{EXP}{eid}/void/", {"reason": "  "}, format="json").status_code == 400
    voided = tenant_a.client.post(f"{EXP}{eid}/void/", {"reason": "Entered twice"}, format="json")
    assert voided.status_code == 200, voided.data
    assert voided.data["status"] == "VOID" and voided.data["void_reason"] == "Entered twice"
    assert tenant_a.client.get(EXP).data["results"] == []
    listed = tenant_a.client.get(EXP + "?include_void=1").data["results"]
    assert [row["id"] for row in listed] == [eid]
    assert Expense.objects.get(pk=eid).number == number  # the number is never reused
    again = tenant_a.client.post(f"{EXP}{eid}/void/", {"reason": "again"}, format="json")
    assert again.status_code == 400
    edit = tenant_a.client.patch(f"{EXP}{eid}/", {"notes": "x"}, format="json")
    assert edit.status_code == 400
    from core.models import AuditEvent

    event = AuditEvent.objects.filter(entity_type="Expense", entity_id=str(eid)).order_by("-id").first()
    assert event and event.metadata.get("event") == "expense.voided"
    assert event.metadata.get("reason") == "Entered twice"


def test_expense_delete_is_a_void(tenant_a, expense_cat):
    created = _expense(tenant_a, expense_cat)
    eid = created.data["id"]
    no_reason = tenant_a.client.delete(f"{EXP}{eid}/")
    assert no_reason.status_code == 400
    gone = tenant_a.client.delete(f"{EXP}{eid}/?reason=Wrong+entry")
    assert gone.status_code in (200, 204)
    row = Expense.objects.get(pk=eid)
    assert row.status == Expense.Status.VOID and row.void_reason == "Wrong entry"


def test_voided_expense_leaves_cash_position_and_bank_matching(tenant_a, expense_cat):
    from reporting.transactions import day_book

    created = _expense(tenant_a, expense_cat, expense_date=timezone.localdate().isoformat())
    assert any(r["txn_type"] == "EXPENSE" for r in day_book(tenant_a.company, timezone.localdate())["rows"])
    tenant_a.client.post(f"{EXP}{created.data['id']}/void/", {"reason": "oops"}, format="json")
    assert not any(r["txn_type"] == "EXPENSE" for r in day_book(tenant_a.company, timezone.localdate())["rows"])
