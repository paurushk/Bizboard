"""ACS-52..55 and the ACS-12 follow-up: fixed asset acquisition, schedule, depreciation operations."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.test import override_settings

from accounting import depreciation
from accounting.models import Account, AccountingPeriod, FixedAsset, JournalEntry
from payments.models import BankAccount
from tests.test_sprint_a_accounting_p1 import books  # noqa: F401

pytestmark = pytest.mark.django_db

FA = "/api/v1/accounting/fixed-assets/"


@pytest.fixture(autouse=True)
def _assets_on():
    with override_settings(ENABLE_FIXED_ASSETS=True):
        yield


def _acct(books, code):  # noqa: F811
    return Account.objects.get(company=books.company, code=code)


def _asset(books, **kw):  # noqa: F811
    body = {
        "name": "Laptop", "acquisition_date": "2026-01-10", "acquisition_cost": "36000.00",
        "useful_life_months": 36, "method": "SLM",
    }
    body.update(kw)
    resp = books.client.post(FA, body, format="json")
    assert resp.status_code == 201, resp.data
    return resp.data


def _lines(entry):
    return {(l.account.code, l.debit, l.credit) for l in entry.lines.all()}


# ------------------------------------------------------------------ ACS-53 acquisition
def test_already_booked_posts_nothing(books):  # noqa: F811
    data = _asset(books)
    assert data["funding"] == "ALREADY_BOOKED" and data["acquisition_journal"] is None
    assert not JournalEntry.objects.filter(company=books.company, purpose="ACQUISITION").exists()


def test_cash_funded_asset_posts_dr_1600_cr_cash(books):  # noqa: F811
    data = _asset(books, funding="CASH")
    entry = JournalEntry.objects.get(pk=data["acquisition_journal"])
    assert entry.entry_date == date(2026, 1, 10)
    assert _lines(entry) == {("1600", Decimal("36000.00"), Decimal("0.00")), ("1100", Decimal("0.00"), Decimal("36000.00"))}


def test_bank_funded_requires_a_bank_and_uses_its_ledger(books):  # noqa: F811
    assert books.client.post(FA, {
        "name": "X", "acquisition_date": "2026-01-10", "acquisition_cost": "100", "useful_life_months": 12, "funding": "BANK",
    }, format="json").status_code == 400
    bank = BankAccount.objects.create(company=books.company, name="HDFC")
    data = _asset(books, funding="BANK", funding_bank_account=bank.id)
    entry = JournalEntry.objects.get(pk=data["acquisition_journal"])
    codes = {c for c, _d, _c in _lines(entry)}
    assert "1600" in codes and any(c.startswith("1500") for c in codes)


def test_supplier_funded_credits_payables_with_the_supplier_tag(books):  # noqa: F811
    from tests.conftest import make_supplier

    supplier = make_supplier(books.company, name="Dell")
    data = _asset(books, funding="SUPPLIER", funding_supplier=supplier.id)
    entry = JournalEntry.objects.get(pk=data["acquisition_journal"])
    payable = entry.lines.get(account__code="2100")
    assert payable.supplier_id == supplier.id and payable.credit == Decimal("36000.00")


def test_other_company_bank_or_supplier_is_rejected(books, tenant_b):  # noqa: F811
    foreign = BankAccount.objects.create(company=tenant_b.company, name="Foreign")
    resp = books.client.post(FA, {
        "name": "X", "acquisition_date": "2026-01-10", "acquisition_cost": "100", "useful_life_months": 12,
        "funding": "BANK", "funding_bank_account": foreign.id,
    }, format="json")
    assert resp.status_code == 400


def test_funding_cannot_change_later(books):  # noqa: F811
    data = _asset(books, funding="CASH")
    assert books.client.patch(f"{FA}{data['id']}/", {"funding": "ALREADY_BOOKED"}, format="json").status_code == 400
    assert books.client.patch(f"{FA}{data['id']}/", {"name": "Laptop Pro"}, format="json").status_code == 200


def test_acquisition_in_a_closed_month_is_refused_and_nothing_is_saved(books):  # noqa: F811
    AccountingPeriod.objects.create(
        company=books.company, name="Jan", start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
        status=AccountingPeriod.Status.CLOSED,
    )
    resp = books.client.post(FA, {
        "name": "X", "acquisition_date": "2026-01-10", "acquisition_cost": "100", "useful_life_months": 12, "funding": "CASH",
    }, format="json")
    assert resp.status_code == 400
    assert not FixedAsset.objects.filter(company=books.company, name="X").exists()


def test_summary_and_register_vs_gl_with_draft_fix(books):  # noqa: F811
    _asset(books, name="Booked", funding="CASH")
    _asset(books, name="Imported")  # never booked
    summary = books.client.get(FA + "summary/").data
    assert summary["count"] == 2 and Decimal(summary["total_cost"]) == Decimal("72000")
    assert Decimal(summary["register_vs_gl"]["cost_difference"]) == Decimal("36000")
    draft = books.client.post(FA + "register-check/draft/", {}, format="json")
    assert draft.status_code == 201, draft.data
    entry = JournalEntry.objects.get(pk=draft.data["journal_id"])
    assert entry.status == JournalEntry.Status.DRAFT
    assert _lines(entry) == {("1600", Decimal("36000.00"), Decimal("0.00")), ("3200", Decimal("0.00"), Decimal("36000.00"))}
    assert books.client.post(f"/api/v1/accounting/journals/{entry.id}/post/").status_code == 200
    assert Decimal(books.client.get(FA + "summary/").data["register_vs_gl"]["cost_difference"]) == 0
    assert books.client.post(FA + "register-check/draft/", {}, format="json").status_code == 400


# ------------------------------------------------------------------ ACS-54 operations
def test_dry_run_then_run_posts_each_missing_month_once(books):  # noqa: F811
    data = _asset(books, acquisition_date="2026-01-01")
    through = "2026-03"
    preview = books.client.post(FA + "run-depreciation/", {"month": through, "dry_run": True}, format="json")
    assert preview.status_code == 200, preview.data
    months = [m["month"] for m in preview.data["assets"][0]["months"]]
    assert months == ["2026-01", "2026-02", "2026-03"]
    assert JournalEntry.objects.filter(company=books.company, purpose__startswith="DEPRECIATION-").count() == 0
    done = books.client.post(FA + "run-depreciation/", {"month": through}, format="json")
    assert done.data["posted"] == 3 and Decimal(done.data["total"]) == Decimal("3000.00")
    again = books.client.post(FA + "run-depreciation/", {"month": through}, format="json")
    assert again.data["posted"] == 0
    asset = FixedAsset.objects.get(pk=data["id"])
    assert asset.depreciated_amount == Decimal("3000.00")


def test_run_reports_a_closed_month_against_its_asset_and_continues(books):  # noqa: F811
    data = _asset(books, acquisition_date="2026-01-01")
    AccountingPeriod.objects.create(
        company=books.company, name="Feb", start_date=date(2026, 2, 1), end_date=date(2026, 2, 28),
        status=AccountingPeriod.Status.CLOSED,
    )
    res = books.client.post(FA + "run-depreciation/", {"month": "2026-03"}, format="json").data
    assert res["posted"] == 2
    row = res["assets"][0]
    assert any(m["month"] == "2026-02" and m["status"] == "blocked" for m in row["months"])
    asset = books.client.get(f"{FA}{data['id']}/").data
    assert asset["depreciation_errors"] and asset["depreciation_errors"][0]["month"] == "2026-02"


def test_cannot_run_a_month_that_has_not_ended(books):  # noqa: F811
    _asset(books)
    resp = books.client.post(FA + "run-depreciation/", {"month": "2099-12"}, format="json")
    assert resp.status_code == 400


def test_run_requires_journal_posting_right(books):  # noqa: F811
    assert books.staff_client.post(FA + "run-depreciation/", {"month": "2026-03"}, format="json").status_code == 403


def test_wdv_narration_uses_the_real_method(books):  # noqa: F811
    _asset(books, name="Truck", acquisition_date="2026-01-01", method="WDV", wdv_annual_rate="15", useful_life_months=96)
    books.client.post(FA + "run-depreciation/", {"month": "2026-01"}, format="json")
    entry = JournalEntry.objects.get(company=books.company, purpose="DEPRECIATION-2026-01")
    assert entry.narration.startswith("WDV depreciation")


def test_schedule_shows_posted_missing_and_projected_months_with_links(books):  # noqa: F811
    data = _asset(books, acquisition_date="2026-01-01", useful_life_months=12, acquisition_cost="12000.00")
    books.client.post(FA + "run-depreciation/", {"month": "2026-02"}, format="json")
    rows = books.client.get(f"{FA}{data['id']}/schedule/").data["rows"]
    assert [r["status"] for r in rows[:2]] == ["posted", "posted"]
    assert rows[0]["journal_id"] and rows[0]["number"]
    assert len(rows) == 12 and Decimal(rows[-1]["accumulated"]) == Decimal("12000.00")
    assert {r["status"] for r in rows[2:]} <= {"missing", "projected"}


def test_leap_year_proration_and_salvage_floor(books):  # noqa: F811
    asset = FixedAsset.objects.create(
        company=books.company, name="Mid", asset_account=_acct(books, "1600"),
        accumulated_depreciation_account=_acct(books, "1650"), depreciation_expense_account=_acct(books, "5300"),
        acquisition_date=date(2024, 2, 15), acquisition_cost=Decimal("2900.00"), useful_life_months=12,
        salvage_value=Decimal("100.00"),
    )
    # 2024 is a leap year: Feb has 29 days, 15 of them in service (15..29).
    amount = depreciation.month_amount(asset, date(2024, 2, 29))
    full = asset.monthly_depreciation
    assert amount == (full * Decimal(15) / Decimal(29)).quantize(Decimal("0.01"))
    asset.depreciated_amount = Decimal("2900.00") - Decimal("100.00")
    assert depreciation.month_amount(asset, date(2024, 12, 31)) == 0


# ------------------------------------------------------------------ ACS-12 follow-up
def test_disposal_charges_the_part_month_first(books):  # noqa: F811
    data = _asset(books, acquisition_date="2026-01-01", acquisition_cost="3100.00", useful_life_months=31, funding="CASH")
    # Run through March; dispose on 15 April: April's part-month (15/30) is charged by the disposal itself.
    books.client.post(FA + "run-depreciation/", {"month": "2026-03"}, format="json")
    resp = books.client.post(f"{FA}{data['id']}/dispose/", {"confirm": True, "disposal_date": "2026-04-15", "charge_part_month": True}, format="json")
    assert resp.status_code == 200, resp.data
    asset = FixedAsset.objects.get(pk=data["id"])
    assert asset.status == FixedAsset.Status.DISPOSED
    april = JournalEntry.objects.get(company=books.company, purpose="DEPRECIATION-2026-04")
    assert april.lines.get(account__code="5300").debit == Decimal("50.00")  # 100/month * 15/30
    assert asset.depreciated_amount == Decimal("350.00")


# ------------------------------------------------------------------ ACS-55
def test_presets_endpoint(books):  # noqa: F811
    data = books.client.get(FA + "presets/").data
    keys = {r["key"] for r in data["results"]}
    assert {"computers", "vehicles", "furniture"} <= keys and "CA" in data["note"]


def test_flag_off_hides_the_whole_surface(books):  # noqa: F811
    with override_settings(ENABLE_FIXED_ASSETS=False):
        assert books.client.get(FA).status_code == 404
