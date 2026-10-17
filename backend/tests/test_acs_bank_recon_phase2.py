"""ACS-40..46: unified bank matching, reconciliation sessions, suggestions, entries, reports."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from accounting import bank_match
from accounting.models import Account, BankReconSession, JournalEntry, JournalLine, JournalLineBankLink
from accounting.services import PostingService
from payments.models import BankAccount, BankLineMatchStatus, BankStatement, BankStatementLine, ReconMatch
from tests.test_sprint_a_accounting_p1 import books  # noqa: F401

pytestmark = pytest.mark.django_db

S = "/api/v1/accounting/bank-recon-sessions/"


def _acct(books, code):  # noqa: F811
    return Account.objects.get(company=books.company, code=code)


class Rig:
    """A bank with a ledger, a statement, two receipts-in-books and the statement lines that cover them."""

    def __init__(self, books):  # noqa: F811
        self.books = books
        self.bank = BankAccount.objects.create(company=books.company, name="HDFC")
        self.ledger = PostingService._bank_gl_account(books.company, self.bank)
        self.statement = BankStatement.objects.create(
            company=books.company, bank_account=self.bank, period_start=date(2026, 6, 1), period_end=date(2026, 6, 30),
        )

    def book(self, amount, day, *, money_in=True, narration="book"):
        other = _acct(self.books, "4100") if money_in else _acct(self.books, "5000")
        amt = Decimal(amount)
        lines = (
            [{"account": self.ledger, "debit": amt}, {"account": other, "credit": amt}]
            if money_in
            else [{"account": other, "debit": amt}, {"account": self.ledger, "credit": amt}]
        )
        self._n = getattr(self, "_n", 0) + 1
        entry = PostingService.post(
            company=self.books.company, source_type="TEST", source_id=self._n, purpose="X",
            entry_date=date(2026, 6, day), user=self.books.owner, narration=narration, lines=lines,
        )
        return entry.lines.get(account=self.ledger)

    def bank_line(self, amount, day, narration="bank", utr=""):
        return BankStatementLine.objects.create(
            company=self.books.company, statement=self.statement, txn_date=date(2026, 6, day),
            amount=Decimal(amount), narration=narration, utr=utr,
        )

    def session(self, closing=None):
        body = {"account": self.ledger.id, "statement": self.statement.id, "statement_date": "2026-06-30"}
        if closing is not None:
            body["statement_closing_balance"] = str(closing)
        resp = self.books.client.post(S, body, format="json")
        assert resp.status_code == 201, resp.data
        return BankReconSession.objects.get(pk=resp.data["id"])


@pytest.fixture
def rig(books):  # noqa: F811
    return Rig(books)


# ------------------------------------------------------------------ ACS-40 shared service
def test_gl_match_marks_line_and_blocks_payments_confirm(rig):
    jl, bl = rig.book("500", 5), rig.bank_line("500", 6)
    session = rig.session(500)
    resp = rig.books.client.post(f"{S}{session.id}/match/", {"journal_line": jl.id, "bank_statement_line": bl.id}, format="json")
    assert resp.status_code == 200, resp.data
    bl.refresh_from_db()
    assert bl.match_status == BankLineMatchStatus.MATCHED
    assert bank_match.line_engine(bl) == "gl"
    with pytest.raises(Exception) as exc:
        bank_match.assert_line_free(bl, engine="payments")
    assert "already matched" in str(exc.value)


def test_payments_match_blocks_gl_match_and_links_the_ledger_line(rig):
    from payments.models import CustomerReceipt
    from tests.conftest import make_customer

    jl = rig.book("500", 5)
    bl = rig.bank_line("500", 6)
    receipt = CustomerReceipt.objects.create(
        company=rig.books.company, customer=make_customer(rig.books.company), amount=Decimal("500"), mode="BANK",
        created_by=rig.books.owner, updated_by=rig.books.owner,
    )
    match = ReconMatch.objects.create(company=rig.books.company, line=bl, receipt=receipt)
    bl.match_status = BankLineMatchStatus.MATCHED
    bl.save()
    session = rig.session(500)
    with pytest.raises(Exception) as exc:
        bank_match.match_gl(rig.books.company, rig.books.owner, session, [jl.id], [bl.id])
    assert "already matched" in str(exc.value)
    assert match.pk


def test_unmatch_clears_both_sides(rig):
    jl, bl = rig.book("500", 5), rig.bank_line("500", 6)
    session = rig.session(500)
    bank_match.match_gl(rig.books.company, rig.books.owner, session, [jl.id], [bl.id])
    resp = rig.books.client.post(f"{S}{session.id}/unmatch/", {"bank_line": bl.id}, format="json")
    assert resp.status_code == 200, resp.data
    jl.refresh_from_db()
    bl.refresh_from_db()
    assert jl.bank_statement_line_id is None and jl.reconciled_at is None
    assert bl.match_status == BankLineMatchStatus.UNMATCHED


def test_repair_command_logic_reports_and_fixes_stale_state(rig):
    bl = rig.bank_line("100", 3)
    bl.match_status = BankLineMatchStatus.MATCHED
    bl.save()
    jl = rig.book("200", 4)
    other = rig.bank_line("200", 4)
    jl.bank_statement_line = other
    jl.save()
    problems = {p["problem"] for p in bank_match.inconsistent_lines(rig.books.company)}
    assert problems == {"marked_matched_without_match", "linked_but_not_marked_matched"}
    result = bank_match.repair(rig.books.company)
    assert result["mark_unmatched"] == 1 and result["mark_matched"] == 1
    assert bank_match.inconsistent_lines(rig.books.company) == []


def test_repair_matched_in_both_needs_a_choice(rig):
    from payments.models import CustomerReceipt
    from tests.conftest import make_customer

    jl, bl = rig.book("500", 5), rig.bank_line("500", 6)
    jl.bank_statement_line = bl
    jl.save()
    receipt = CustomerReceipt.objects.create(
        company=rig.books.company, customer=make_customer(rig.books.company), amount=Decimal("500"), mode="BANK",
        created_by=rig.books.owner, updated_by=rig.books.owner,
    )
    ReconMatch.objects.create(company=rig.books.company, line=bl, receipt=receipt)
    bl.match_status = BankLineMatchStatus.MATCHED
    bl.save()
    assert bank_match.repair(rig.books.company)["left_for_review"] == 1
    assert bank_match.repair(rig.books.company, prefer="gl")["resolved_both"] == 1
    assert not ReconMatch.objects.filter(line=bl).exists()


# ------------------------------------------------------------------ ACS-41 session
def test_session_summary_difference_is_zero_when_everything_ties(rig):
    j1, j2 = rig.book("500", 5), rig.book("300", 10, money_in=False)
    outstanding = rig.book("200", 29)  # deposit in transit
    b1, b2 = rig.bank_line("500", 6), rig.bank_line("-300", 11)
    session = rig.session(closing=200)  # 500 - 300 on the bank; the 200 has not cleared
    bank_match.match_gl(rig.books.company, rig.books.owner, session, [j1.id], [b1.id])
    bank_match.match_gl(rig.books.company, rig.books.owner, session, [j2.id], [b2.id])
    summary = bank_match.session_summary(session)
    assert summary["gl_balance_as_at"] == "400.00"
    assert summary["outstanding_deposits"] == "200.00"
    assert summary["difference"] == "0.00"
    session.refresh_from_db()
    assert session.status == BankReconSession.Status.RECONCILED
    assert outstanding.pk


def test_finalise_requires_zero_difference_then_locks_matches(rig):
    jl, bl = rig.book("500", 5), rig.bank_line("500", 6)
    session = rig.session(closing=450)  # the bank says 450, books say 500
    bank_match.match_gl(rig.books.company, rig.books.owner, session, [jl.id], [bl.id])
    refused = rig.books.client.post(f"{S}{session.id}/finalise/", {}, format="json")
    assert refused.status_code == 400 and "difference" in str(refused.data).lower()
    session.statement_closing_balance = Decimal("500")
    session.save()
    ok = rig.books.client.post(f"{S}{session.id}/finalise/", {}, format="json")
    assert ok.status_code == 200, ok.data
    session.refresh_from_db()
    assert session.status == BankReconSession.Status.FINALISED and session.finalised_by_id
    locked = rig.books.client.post(f"{S}{session.id}/unmatch/", {"bank_line": bl.id}, format="json")
    assert locked.status_code == 400 and "finalised" in str(locked.data).lower()
    assert rig.books.staff_client.post(f"{S}{session.id}/reopen/", {"reason": "x"}, format="json").status_code == 403
    assert rig.books.client.post(f"{S}{session.id}/reopen/", {}, format="json").status_code == 400
    reopened = rig.books.client.post(f"{S}{session.id}/reopen/", {"reason": "wrong match"}, format="json")
    assert reopened.status_code == 200
    assert rig.books.client.post(f"{S}{session.id}/unmatch/", {"bank_line": bl.id}, format="json").status_code == 200


def test_small_difference_can_be_written_off_by_an_owner_only(rig):
    jl, bl = rig.book("500", 5), rig.bank_line("500", 6)
    session = rig.session(closing=Decimal("495.00"))
    bank_match.match_gl(rig.books.company, rig.books.owner, session, [jl.id], [bl.id])
    assert bank_match.session_summary(session)["difference"] == "-5.00"
    forbidden = rig.books.staff_client.post(f"{S}{session.id}/finalise/", {"write_off": True}, format="json")
    assert forbidden.status_code in (400, 403)
    ok = rig.books.client.post(f"{S}{session.id}/finalise/", {"write_off": True}, format="json")
    assert ok.status_code == 200, ok.data
    session.refresh_from_db()
    assert session.write_off_entry_id and session.status == BankReconSession.Status.FINALISED
    assert bank_match.session_summary(session)["difference"] == "0.00"


def test_large_difference_cannot_be_written_off(rig):
    jl, bl = rig.book("500", 5), rig.bank_line("500", 6)
    session = rig.session(closing=Decimal("400.00"))
    bank_match.match_gl(rig.books.company, rig.books.owner, session, [jl.id], [bl.id])
    resp = rig.books.client.post(f"{S}{session.id}/finalise/", {"write_off": True}, format="json")
    assert resp.status_code == 400 and "written off" in str(resp.data).lower()


def test_as_at_balance_ignores_later_entries(rig):
    rig.book("500", 5)
    later = PostingService.post(
        company=rig.books.company, source_type="TEST", source_id=99, purpose="X", entry_date=date(2026, 7, 5),
        user=rig.books.owner, narration="july",
        lines=[{"account": rig.ledger, "debit": Decimal("40")}, {"account": _acct(rig.books, "4100"), "credit": Decimal("40")}],
    )
    session = rig.session(closing=500)
    assert bank_match.session_summary(session)["gl_balance_as_at"] == "500.00"
    assert later.pk


# ------------------------------------------------------------------ ACS-42 many-to-one
def test_many_ledger_lines_to_one_bank_line_when_totals_equal(rig):
    j1, j2 = rig.book("300", 5), rig.book("200", 6)
    bl = rig.bank_line("500", 7)
    session = rig.session(closing=500)
    resp = rig.books.client.post(f"{S}{session.id}/match-many/", {"journal_lines": [j1.id, j2.id], "bank_lines": [bl.id]}, format="json")
    assert resp.status_code == 200, resp.data
    assert JournalLine.objects.filter(bank_statement_line=bl).count() == 2


def test_one_ledger_line_to_many_bank_lines_and_group_unmatch(rig):
    jl = rig.book("500", 5)
    b1, b2 = rig.bank_line("300", 6), rig.bank_line("200", 7)
    session = rig.session(closing=500)
    resp = rig.books.client.post(f"{S}{session.id}/match-many/", {"journal_lines": [jl.id], "bank_lines": [b1.id, b2.id]}, format="json")
    assert resp.status_code == 200, resp.data
    assert JournalLineBankLink.objects.filter(journal_line=jl).count() == 1
    rig.books.client.post(f"{S}{session.id}/unmatch/", {"bank_line": b2.id}, format="json")
    jl.refresh_from_db()
    b1.refresh_from_db()
    assert jl.bank_statement_line_id is None
    assert b1.match_status == BankLineMatchStatus.UNMATCHED
    assert not JournalLineBankLink.objects.exists()


def test_unequal_totals_and_many_to_many_are_refused(rig):
    j1, j2 = rig.book("300", 5), rig.book("200", 6)
    b1, b2 = rig.bank_line("500", 7), rig.bank_line("1", 7)
    session = rig.session(closing=500)
    assert rig.books.client.post(f"{S}{session.id}/match-many/", {"journal_lines": [j1.id], "bank_lines": [b1.id]}, format="json").status_code == 400
    assert rig.books.client.post(f"{S}{session.id}/match-many/", {"journal_lines": [j1.id, j2.id], "bank_lines": [b1.id, b2.id]}, format="json").status_code == 400


def test_workspace_lists_are_filterable(rig):
    rig.book("500", 5, narration="rent")
    rig.book("123.45", 6, narration="misc")
    rig.bank_line("500", 6, narration="UPI rent")
    session = rig.session(closing=0)
    ledger = rig.books.client.get(f"{S}{session.id}/ledger-lines/", {"q": "rent"}).data
    assert [r["narration"] for r in ledger["results"]] == ["rent"]
    only_amount = rig.books.client.get(f"{S}{session.id}/ledger-lines/", {"amount": "123.45"}).data
    assert len(only_amount["results"]) == 1
    bank = rig.books.client.get(f"{S}{session.id}/statement-lines/", {"q": "upi"}).data
    assert len(bank["results"]) == 1


# ------------------------------------------------------------------ ACS-43 suggestions
def test_suggestions_rank_by_amount_date_and_words_and_accept_high(rig):
    jl = rig.book("500", 5, narration="Rent June landlord")
    rig.book("500", 20, narration="other")
    bl = rig.bank_line("500", 6, narration="NEFT landlord rent")
    session = rig.session(closing=1000)
    data = rig.books.client.get(f"{S}{session.id}/suggestions/").data["results"]
    top = max(data, key=lambda r: r["score"])
    assert top["bank_line"] == bl.id and top["journal_line"] == jl.id
    assert "landlord" in top["shared_words"] and top["confidence"] == "high"
    preview = rig.books.client.post(f"{S}{session.id}/accept-suggestions/", {"confidence": "high", "preview": True}, format="json")
    assert preview.data["count"] == 1
    done = rig.books.client.post(f"{S}{session.id}/accept-suggestions/", {"confidence": "high"}, format="json")
    assert done.data["matched"] == 1
    bl.refresh_from_db()
    assert bl.match_status == BankLineMatchStatus.MATCHED


def test_suggestion_never_matches_different_amounts(rig):
    rig.book("500", 5)
    rig.bank_line("501", 5)
    session = rig.session()
    assert rig.books.client.get(f"{S}{session.id}/suggestions/").data["results"] == []


# ------------------------------------------------------------------ ACS-44 create entry
def test_create_entry_from_statement_line_posts_and_matches(rig):
    bl = rig.bank_line("-45.00", 9, narration="SMS charges")
    session = rig.session(closing=-45)
    charges = _acct(rig.books, "5200")
    resp = rig.books.client.post(f"{S}{session.id}/create-entry/", {"bank_line": bl.id, "account": charges.id}, format="json")
    assert resp.status_code == 201, resp.data
    bl.refresh_from_db()
    assert bl.match_status == BankLineMatchStatus.MATCHED
    entry = JournalEntry.objects.get(pk=resp.data["journal_entry"])
    assert {(l.account.code, l.debit, l.credit) for l in entry.lines.all()} >= {("5200", Decimal("45.00"), Decimal("0.00"))}
    assert bank_match.session_summary(session)["difference"] == "0.00"
    again = rig.books.client.post(f"{S}{session.id}/create-entry/", {"bank_line": bl.id, "account": charges.id}, format="json")
    assert again.status_code == 400


def test_create_entry_refuses_party_control_accounts(rig):
    bl = rig.bank_line("100", 9)
    session = rig.session()
    resp = rig.books.client.post(f"{S}{session.id}/create-entry/", {"bank_line": bl.id, "account": _acct(rig.books, "1200").id}, format="json")
    assert resp.status_code == 400 and "receipt" in str(resp.data).lower()


# ------------------------------------------------------------------ ACS-45/46 context and report
def test_session_list_shows_context_and_filters(rig):
    session = rig.session(closing=0)
    rows = rig.books.client.get(S, {"status": "OPEN"}).data["results"]
    assert rows[0]["account_name"].startswith("Bank")
    assert "HDFC" in rows[0]["statement_name"]
    assert rows[0]["difference"] is not None
    assert rig.books.client.get(S, {"status": "FINALISED"}).data["results"] == []
    assert session.pk


def test_report_json_xlsx_pdf(rig):
    rig.book("500", 5)
    rig.bank_line("-20", 8, narration="charge")
    session = rig.session(closing=-20)
    data = rig.books.client.get(f"{S}{session.id}/report/").data
    assert data["outstanding_items"][0]["amount"] == "500.00"
    assert data["unrecorded_items"][0]["amount"] == "-20.00"
    xlsx = rig.books.client.get(f"{S}{session.id}/report/", {"file": "xlsx"})
    assert xlsx.status_code == 200 and xlsx["Content-Type"].startswith("application/vnd.openxml")
    pdf = rig.books.client.get(f"{S}{session.id}/report/", {"file": "pdf"})
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


def test_cross_company_lines_are_refused(rig, tenant_b):
    other = BankAccount.objects.create(company=tenant_b.company, name="Other")
    stmt = BankStatement.objects.create(company=tenant_b.company, bank_account=other)
    foreign = BankStatementLine.objects.create(
        company=tenant_b.company, statement=stmt, txn_date=date(2026, 6, 1), amount=Decimal("500"),
    )
    jl = rig.book("500", 5)
    session = rig.session(closing=500)
    resp = rig.books.client.post(f"{S}{session.id}/match/", {"journal_line": jl.id, "bank_statement_line": foreign.id}, format="json")
    assert resp.status_code == 400


def test_closing_balance_and_date_can_be_set_until_finalised(rig):
    jl, bl = rig.book("500", 5), rig.bank_line("500", 6)
    session = rig.session()
    bank_match.match_gl(rig.books.company, rig.books.owner, session, [jl.id], [bl.id])
    resp = rig.books.client.patch(f"{S}{session.id}/", {"statement_closing_balance": "500.00", "account": 1}, format="json")
    assert resp.status_code == 200, resp.data
    session.refresh_from_db()
    assert session.statement_closing_balance == Decimal("500.00") and session.account_id == rig.ledger.id
    assert session.status == BankReconSession.Status.RECONCILED
    rig.books.client.post(f"{S}{session.id}/finalise/", {}, format="json")
    assert rig.books.client.patch(f"{S}{session.id}/", {"statement_closing_balance": "1"}, format="json").status_code == 400
