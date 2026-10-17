"""ACS-50, ACS-51, ACS-17: chart management, cost centres, expense tax / register / recurring."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from accounting import recurring
from accounting.models import Account, CostCenter, Expense, JournalEntry, JournalLine, RecurringExpense
from accounting.services import PostingService
from masters.models import ExpenseCategory
from tests.test_sprint_a_accounting_p1 import books  # noqa: F401

pytestmark = pytest.mark.django_db

A = "/api/v1/accounting/accounts/"
CC = "/api/v1/accounting/cost-centers/"
EXP = "/api/v1/accounting/expenses/"
REC = "/api/v1/accounting/recurring-expenses/"


def _acct(books, code):  # noqa: F811
    return Account.objects.get(company=books.company, code=code)


# ------------------------------------------------------------------ ACS-50 chart
def test_duplicate_code_gives_a_clear_message(books):  # noqa: F811
    first = books.client.post(A, {"code": "5950", "name": "Rent", "type": "EXPENSE"}, format="json")
    assert first.status_code == 201, first.data
    dup = books.client.post(A, {"code": "5950", "name": "Other", "type": "EXPENSE"}, format="json")
    assert dup.status_code == 400 and "already used by Rent" in str(dup.data)


def test_code_and_type_freeze_after_postings_but_name_stays_editable(books):  # noqa: F811
    acct = Account.objects.create(company=books.company, code="5951", name="Travel", type="EXPENSE")
    assert books.client.patch(f"{A}{acct.id}/", {"code": "5952"}, format="json").status_code == 200
    PostingService.post(
        company=books.company, source_type="TEST", source_id=1, purpose="X", entry_date=date(2026, 6, 1), user=books.owner,
        lines=[{"account": acct, "debit": Decimal("10")}, {"account": _acct(books, "1100"), "credit": Decimal("10")}],
    )
    assert books.client.patch(f"{A}{acct.id}/", {"code": "5953"}, format="json").status_code == 400
    assert books.client.patch(f"{A}{acct.id}/", {"type": "ASSET"}, format="json").status_code == 400
    assert books.client.patch(f"{A}{acct.id}/", {"name": "Travel and stay"}, format="json").status_code == 200


def test_cannot_deactivate_with_balance_but_transfer_draft_then_post_unlocks_it(books):  # noqa: F811
    acct = Account.objects.create(company=books.company, code="5954", name="Old", type="EXPENSE")
    target = Account.objects.create(company=books.company, code="5955", name="New", type="EXPENSE")
    PostingService.post(
        company=books.company, source_type="TEST", source_id=2, purpose="X", entry_date=date(2026, 6, 1), user=books.owner,
        lines=[{"account": acct, "debit": Decimal("75")}, {"account": _acct(books, "1100"), "credit": Decimal("75")}],
    )
    refused = books.client.patch(f"{A}{acct.id}/", {"is_active": False}, format="json")
    assert refused.status_code == 400 and "balance" in str(refused.data)
    draft = books.client.post(f"{A}{acct.id}/transfer-balance/", {"to_account": target.id, "entry_date": "2026-06-02"}, format="json")
    assert draft.status_code == 201, draft.data
    assert books.client.post(f"/api/v1/accounting/journals/{draft.data['journal_id']}/post/").status_code == 200
    assert books.client.patch(f"{A}{acct.id}/", {"is_active": False}, format="json").status_code == 200


def test_system_account_cannot_be_edited_and_parent_rules(books):  # noqa: F811
    cash = _acct(books, "1100")
    assert books.client.patch(f"{A}{cash.id}/", {"name": "x"}, format="json").status_code == 400
    a = Account.objects.create(company=books.company, code="5960", name="A", type="EXPENSE")
    b = Account.objects.create(company=books.company, code="5961", name="B", type="EXPENSE", parent=a)
    assert books.client.patch(f"{A}{a.id}/", {"parent": b.id}, format="json").status_code == 400  # loop
    assert books.client.patch(f"{A}{a.id}/", {"parent": a.id}, format="json").status_code == 400
    wrong = books.client.post(A, {"code": "5962", "name": "C", "type": "ASSET", "parent": a.id}, format="json")
    assert wrong.status_code == 400


def test_list_filters_balance_and_export(books):  # noqa: F811
    acct = Account.objects.create(company=books.company, code="5970", name="Stationery", type="EXPENSE")
    PostingService.post(
        company=books.company, source_type="TEST", source_id=3, purpose="X", entry_date=date(2026, 6, 1), user=books.owner,
        lines=[{"account": acct, "debit": Decimal("40")}, {"account": _acct(books, "1100"), "credit": Decimal("40")}],
    )
    data = books.client.get(A, {"q": "Stationery", "with_balance": "1"}).data["results"]
    assert len(data) == 1 and data[0]["balance"] == "40.00" and data[0]["has_postings"] is True
    early = books.client.get(A, {"q": "Stationery", "with_balance": "1", "as_of": "2026-05-31"}).data["results"]
    assert early[0]["balance"] == "0.00"
    inactive = books.client.get(A, {"active": "false"}).data["results"]
    assert all(not r["is_active"] for r in inactive)
    csv = books.client.get(A + "export/", {"q": "Stationery"})
    assert csv.status_code == 200 and "Stationery" in csv.content.decode()
    assert books.staff_client.get(A + "export/").status_code in (200, 403)


# ------------------------------------------------------------------ ACS-51 cost centres
def test_cost_centre_duplicate_edit_deactivate_usage_and_loop(books):  # noqa: F811
    one = books.client.post(CC, {"code": "NORTH", "name": "North"}, format="json")
    assert one.status_code == 201, one.data
    dup = books.client.post(CC, {"code": "north", "name": "Again"}, format="json")
    assert dup.status_code == 400 and "already used" in str(dup.data)
    child = books.client.post(CC, {"code": "N1", "name": "North shop", "parent": one.data["id"]}, format="json")
    assert child.status_code == 201
    assert books.client.patch(f"{CC}{one.data['id']}/", {"parent": child.data["id"]}, format="json").status_code == 400
    assert books.client.patch(f"{CC}{one.data['id']}/", {"is_active": False}, format="json").status_code == 400
    assert books.client.patch(f"{CC}{child.data['id']}/", {"is_active": False}, format="json").status_code == 200
    assert books.client.patch(f"{CC}{one.data['id']}/", {"name": "North region"}, format="json").status_code == 200
    rows = {r["code"]: r for r in books.client.get(CC).data["results"]}
    assert rows["NORTH"]["usage"] == {"journal_lines": 0, "invoices": 0, "expenses": 0}


def test_cost_centre_report_matches_pnl_and_shows_unallocated(books):  # noqa: F811
    cc = CostCenter.objects.create(company=books.company, code="S1", name="Shop 1")
    sales, cash, cogs = _acct(books, "4100"), _acct(books, "1100"), _acct(books, "5400")
    PostingService.post(
        company=books.company, source_type="TEST", source_id=4, purpose="X", entry_date=date(2026, 6, 5), user=books.owner,
        lines=[
            {"account": cash, "debit": Decimal("1000")},
            {"account": sales, "credit": Decimal("700"), "cost_center": cc},
            {"account": sales, "credit": Decimal("300")},
        ],
    )
    PostingService.post(
        company=books.company, source_type="TEST", source_id=5, purpose="X", entry_date=date(2026, 6, 6), user=books.owner,
        lines=[{"account": cogs, "debit": Decimal("200"), "cost_center": cc}, {"account": cash, "credit": Decimal("200")}],
    )
    rep = books.client.get(CC + "report/", {"date_from": "2026-06-01", "date_to": "2026-06-30"}).data
    by_code = {r["code"]: r for r in rep["results"]}
    assert Decimal(by_code["S1"]["income"]) == 700 and Decimal(by_code["S1"]["net"]) == 500
    assert Decimal(by_code[""]["income"]) == 300 and by_code[""]["name"] == "Unallocated"
    assert Decimal(rep["totals"]["net"]) == 800


# ------------------------------------------------------------------ ACS-17 expenses
def _cat(books, name="Rent"):  # noqa: F811
    return ExpenseCategory.objects.get_or_create(company=books.company, name=name)[0]


def _enable(books, start=date(2026, 1, 1)):  # noqa: F811
    books.company.expense_gl_start_date = start
    books.company.save(update_fields=["expense_gl_start_date"])


def test_expense_with_gst_itc_and_tds_posts_split_lines(books):  # noqa: F811
    _enable(books)
    body = {
        "category": _cat(books).id, "expense_date": "2026-06-10", "amount": "1180.00", "party_name": "Landlord",
        "cgst_amount": "90.00", "sgst_amount": "90.00", "gst_rate": "18", "itc_eligible": True,
        "supplier_gstin": "27AAPFU0939F1ZV", "tds_section": "194I", "tds_amount": "100.00",
    }
    resp = books.client.post(EXP, body, format="json")
    assert resp.status_code == 201, resp.data
    entry = JournalEntry.objects.get(pk=Expense.objects.get(pk=resp.data["id"]).journal_entry_id)
    lines = {(l.account.code, l.debit, l.credit) for l in entry.lines.all()}
    assert ("5000", Decimal("1000.00"), Decimal("0.00")) in lines
    assert ("1310", Decimal("90.00"), Decimal("0.00")) in lines
    assert ("1320", Decimal("90.00"), Decimal("0.00")) in lines
    assert ("2265", Decimal("0.00"), Decimal("100.00")) in lines
    assert ("1100", Decimal("0.00"), Decimal("1080.00")) in lines
    assert sum(l.debit for l in entry.lines.all()) == sum(l.credit for l in entry.lines.all())


def test_gst_without_itc_stays_in_the_expense(books):  # noqa: F811
    _enable(books)
    resp = books.client.post(EXP, {
        "category": _cat(books).id, "expense_date": "2026-06-10", "amount": "118.00", "igst_amount": "18.00",
        "itc_eligible": False,
    }, format="json")
    assert resp.status_code == 201, resp.data
    entry = JournalEntry.objects.get(pk=Expense.objects.get(pk=resp.data["id"]).journal_entry_id)
    assert {(l.account.code, l.debit) for l in entry.lines.filter(debit__gt=0)} == {("5000", Decimal("118.00"))}


def test_tax_validation_rules(books):  # noqa: F811
    base = {"category": _cat(books).id, "expense_date": "2026-06-10", "amount": "100.00"}
    for extra, _key in (
        ({"igst_amount": "5", "cgst_amount": "2.5", "sgst_amount": "2.5"}, "igst_amount"),
        ({"cgst_amount": "5", "sgst_amount": "3"}, "sgst_amount"),
        ({"igst_amount": "200"}, "cgst_amount"),
        ({"tds_amount": "10"}, "tds_section"),
        ({"tds_amount": "500", "tds_section": "194C"}, "tds_amount"),
        ({"igst_amount": "5", "itc_eligible": True}, "supplier_gstin"),
        ({"supplier_gstin": "BAD"}, "supplier_gstin"),
    ):
        resp = books.client.post(EXP, {**base, **extra}, format="json")
        assert resp.status_code == 400, (extra, resp.data)


def test_cost_centre_flows_into_the_ledger_line(books):  # noqa: F811
    _enable(books)
    cc = CostCenter.objects.create(company=books.company, code="S2", name="Shop 2")
    resp = books.client.post(EXP, {"category": _cat(books).id, "expense_date": "2026-06-10", "amount": "50.00", "cost_center": cc.id}, format="json")
    assert resp.status_code == 201, resp.data
    entry = JournalEntry.objects.get(pk=Expense.objects.get(pk=resp.data["id"]).journal_entry_id)
    assert entry.lines.get(account__code="5000").cost_center_id == cc.id
    assert JournalLine.objects.filter(entry=entry, cost_center__isnull=False).count() == 1


def test_other_company_ids_are_rejected(books, tenant_b):  # noqa: F811
    foreign_cat = ExpenseCategory.objects.create(company=tenant_b.company, name="Foreign")
    resp = books.client.post(EXP, {"category": foreign_cat.id, "expense_date": "2026-06-10", "amount": "10"}, format="json")
    assert resp.status_code == 400
    foreign_cc = CostCenter.objects.create(company=tenant_b.company, code="X", name="X")
    resp = books.client.post(EXP, {"category": _cat(books).id, "expense_date": "2026-06-10", "amount": "10", "cost_center": foreign_cc.id}, format="json")
    assert resp.status_code == 400


def test_register_search_filters_total_and_export(books):  # noqa: F811
    cat = _cat(books)
    for n, (party, amt, _mode) in enumerate((("Alpha", "100", "CASH"), ("Beta", "250", "CASH"), ("Alpha two", "50", "CASH"))):
        books.client.post(EXP, {"category": cat.id, "expense_date": f"2026-06-0{n + 1}", "amount": amt, "party_name": party}, format="json")
    data = books.client.get(EXP, {"q": "alpha"}).data
    assert data["count"] == 2 and Decimal(data["filtered_total"]) == Decimal("150")
    assert Decimal(books.client.get(EXP).data["filtered_total"]) == Decimal("400")
    csv = books.client.get(EXP + "export/", {"q": "beta"})
    assert csv.status_code == 200 and "Beta" in csv.content.decode() and "Alpha" not in csv.content.decode()
    assert books.client.get(EXP + "export/", {"file": "xlsx"}).status_code == 200


def test_recurring_generates_each_due_date_once(books):  # noqa: F811
    _enable(books)
    cat = _cat(books)
    today = timezone.localdate()
    start = (today.replace(day=1) - timedelta(days=62)).replace(day=5)
    resp = books.client.post(REC, {"category": cat.id, "amount": "500.00", "party_name": "Landlord", "frequency": "MONTHLY", "next_date": start.isoformat()}, format="json")
    assert resp.status_code == 201, resp.data
    due = books.client.get(REC + "due/").data
    assert due["count"] == 1
    first = books.client.post(REC + "create-due/", {}, format="json").data
    assert len(first["created"]) >= 2 and first["skipped"] == []
    second = books.client.post(REC + "create-due/", {}, format="json").data
    assert second["created"] == []
    assert Expense.objects.filter(company=books.company, recurring_template_id=resp.data["id"]).count() == len(first["created"])
    template = RecurringExpense.objects.get(pk=resp.data["id"])
    assert template.next_date > today
    assert all(Expense.objects.get(pk=c["expense"]).journal_entry_id for c in first["created"])


def test_advance_handles_month_ends():
    assert recurring.advance(date(2026, 1, 31), "MONTHLY") == date(2026, 2, 28)
    assert recurring.advance(date(2026, 11, 30), "QUARTERLY") == date(2027, 2, 28)
    assert recurring.advance(date(2024, 2, 29), "YEARLY") == date(2025, 2, 28)


def test_category_reorder_and_owner_only(books):  # noqa: F811
    a, b = _cat(books, "A"), _cat(books, "B")
    url = "/api/v1/masters/expense-categories/"
    assert books.client.patch(f"{url}{b.id}/", {"sort_order": 1}, format="json").status_code == 200
    assert books.client.patch(f"{url}{a.id}/", {"sort_order": 2}, format="json").status_code == 200
    names = [r["name"] for r in books.client.get(url).data["results"] if r["name"] in ("A", "B")]
    assert names == ["B", "A"]
    assert books.staff_client.patch(f"{url}{a.id}/", {"name": "Z"}, format="json").status_code == 403
