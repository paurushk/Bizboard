"""ACS-40..46: the one place that matches, unmatches and reconciles bank statement lines.

Two engines used to write the same line independently: the payments screen (receipt / supplier
payment -> ``ReconMatch``) and the ledger screen (``JournalLine.bank_statement_line``). Both now
come through here, so a statement line can be matched by exactly one of them at a time and
an unmatch clears both sides.
"""
from __future__ import annotations

import io
import re
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from core.exceptions import BusinessRuleError

from .models import (
    Account,
    BankReconSession,
    JournalEntry,
    JournalLine,
    JournalLineBankLink,
)

ZERO = Decimal("0.00")
STATUSES_IN_BOOKS = (JournalEntry.Status.POSTED, JournalEntry.Status.REVERSED)


def _q(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def _signed(jl: JournalLine) -> Decimal:
    return _q(jl.debit) - _q(jl.credit)


def _models():
    from payments.models import BankLineMatchStatus, BankStatementLine, ReconMatch

    return BankLineMatchStatus, BankStatementLine, ReconMatch


# --------------------------------------------------------------------- state of one line
def line_engine(bank_line) -> str | None:
    """Which engine owns this statement line: 'payments', 'gl' or None (free)."""
    _status, _line, ReconMatch = _models()
    if ReconMatch.objects.filter(line=bank_line).exists():
        return "payments"
    if JournalLine.objects.filter(bank_statement_line=bank_line).exists() or JournalLineBankLink.objects.filter(
        bank_line=bank_line
    ).exists():
        return "gl"
    return None


def assert_line_free(bank_line, *, engine: str) -> None:
    """Raise unless ``bank_line`` can be taken by ``engine`` right now."""
    status, _line, _match = _models()
    owner = line_engine(bank_line)
    if owner is not None:
        where = "the payments reconciliation (receipt or supplier payment)" if owner == "payments" else "the ledger reconciliation"
        raise BusinessRuleError(
            f"This statement line is already matched in {where}. Unmatch it there first.",
            code="bank_line_already_matched",
        )
    if bank_line.match_status == status.IGNORED:
        raise BusinessRuleError("This statement line is ignored. Restore it before matching.", code="bank_line_ignored")
    if bank_line.match_status == status.MATCHED:
        # MATCHED with no owner is stale state; the repair command lists it.
        raise BusinessRuleError(
            "This statement line is marked matched but has no match. Run the bank-match repair.",
            code="bank_line_stale_match",
        )


def _finalised_for_statement(statement_id: int) -> bool:
    return BankReconSession.objects.filter(statement_id=statement_id, status=BankReconSession.Status.FINALISED).exists()


# --------------------------------------------------------------------- ledger match
@transaction.atomic
def match_gl(company, user, session: BankReconSession, journal_line_ids, bank_line_ids) -> dict:
    """Match ledger lines to statement lines: 1:1, many ledger lines : 1 bank line, or 1 ledger line : many bank lines."""
    _status, BankStatementLine, _match = _models()
    status = _status
    if session.status == BankReconSession.Status.FINALISED:
        raise BusinessRuleError("This reconciliation is finalised. Reopen it to change matches.", code="recon_finalised")
    jl_ids = sorted({int(i) for i in journal_line_ids or []})
    bl_ids = sorted({int(i) for i in bank_line_ids or []})
    if not jl_ids or not bl_ids:
        raise BusinessRuleError("Choose at least one ledger line and one statement line.")
    if len(jl_ids) > 1 and len(bl_ids) > 1:
        raise BusinessRuleError("Match one line on one side to many on the other, not many to many.", code="recon_many_to_many")
    jls = list(
        JournalLine.objects.select_for_update()
        .filter(company=company, pk__in=jl_ids, account=session.account, entry__status=JournalEntry.Status.POSTED)
        .select_related("entry")
    )
    bls = list(
        BankStatementLine.objects.select_for_update().filter(company=company, pk__in=bl_ids, statement=session.statement)
    )
    if len(jls) != len(jl_ids):
        raise BusinessRuleError("A ledger line is not on this bank ledger or is not posted.")
    if len(bls) != len(bl_ids):
        raise BusinessRuleError("A statement line does not belong to this reconciliation's statement.")
    for jl in jls:
        if jl.bank_statement_line_id is not None or jl.reconciled_at is not None:
            raise BusinessRuleError("A ledger line is already reconciled.", code="journal_line_reconciled")
    for bl in bls:
        assert_line_free(bl, engine="gl")
    gl_total = sum((_signed(j) for j in jls), ZERO)
    bank_total = sum((_q(b.amount) for b in bls), ZERO)
    if gl_total != bank_total:
        raise BusinessRuleError(
            f"The selected ledger lines total {gl_total} but the statement lines total {bank_total}. They must be equal.",
            code="recon_total_mismatch",
        )
    now = timezone.now()
    if len(jls) == 1:
        jl = jls[0]
        jl.bank_statement_line = bls[0]
        jl.reconciled_at = now
        jl.save(update_fields=["bank_statement_line", "reconciled_at"])
        for extra in bls[1:]:
            JournalLineBankLink.objects.create(company=company, journal_line=jl, bank_line=extra)
    else:
        for jl in jls:
            jl.bank_statement_line = bls[0]
            jl.reconciled_at = now
            jl.save(update_fields=["bank_statement_line", "reconciled_at"])
    for bl in bls:
        bl.match_status = status.MATCHED
        bl.save(update_fields=["match_status", "updated_at"])
    _audit(company, user, "UPDATE", "BankReconSession", session.pk, f"matched {len(jls)} ledger / {len(bls)} statement line(s)")
    refresh_status(session)
    return {"ledger_lines": len(jls), "statement_lines": len(bls), "total": str(gl_total)}


def link_document_gl_line(company, match) -> None:
    """Payments engine: tie the receipt / payment's own bank ledger line to the statement line.

    Without this the matched document would still show as an outstanding item in the ledger
    reconciliation of the same bank.
    """
    from .services import PostingService

    line = match.line
    if match.receipt_id:
        source_type, source_id = "CUSTOMER_RECEIPT", match.receipt_id
    elif match.supplier_payment_id:
        source_type, source_id = "SUPPLIER_PAYMENT", match.supplier_payment_id
    else:
        return
    entry = (
        JournalEntry.objects.filter(
            company=company, source_type=source_type, source_id=source_id, purpose="CREATE",
            status__in=STATUSES_IN_BOOKS,
        )
        .order_by("-id")
        .first()
    )
    if entry is None:
        return
    bank_account = line.statement.bank_account
    accounts = {
        PostingService._bank_gl_account(company, bank_account, entry.entry_date).pk,
        PostingService._bank_gl_account(company, bank_account, None).pk,
    }
    target = _q(line.amount)
    for jl in entry.lines.filter(account_id__in=accounts, bank_statement_line__isnull=True, reconciled_at__isnull=True):
        if _signed(jl) == target:
            jl.bank_statement_line = line
            jl.reconciled_at = timezone.now()
            jl.save(update_fields=["bank_statement_line", "reconciled_at"])
            return


def _release_group(jl: JournalLine) -> None:
    status = _models()[0]
    _s, BankStatementLine, _m = _models()
    extra_ids = list(jl.extra_bank_links.values_list("bank_line_id", flat=True))
    if jl.bank_statement_line_id:
        extra_ids.append(jl.bank_statement_line_id)
    jl.extra_bank_links.all().delete()
    if extra_ids:
        BankStatementLine.objects.filter(pk__in=extra_ids).update(match_status=status.UNMATCHED, updated_at=timezone.now())
    jl.bank_statement_line = None
    jl.reconciled_at = None
    jl.save(update_fields=["bank_statement_line", "reconciled_at"])


@transaction.atomic
def unmatch_line(company, user, bank_line) -> dict:
    """Undo whatever matched this statement line, on both engines."""
    status, BankStatementLine, ReconMatch = _models()
    bank_line = BankStatementLine.objects.select_for_update().get(pk=bank_line.pk, company=company)
    if _finalised_for_statement(bank_line.statement_id):
        raise BusinessRuleError("This statement is finalised. Reopen the reconciliation first.", code="recon_finalised")
    cleared = {"payments": False, "ledger_lines": 0}
    match = ReconMatch.objects.filter(company=company, line=bank_line).first()
    if match is not None:
        match.delete()
        cleared["payments"] = True
    group = list(JournalLine.objects.select_for_update().filter(company=company, bank_statement_line=bank_line))
    extra = JournalLineBankLink.objects.filter(company=company, bank_line=bank_line).select_related("journal_line").first()
    if extra is not None:
        group.append(JournalLine.objects.select_for_update().get(pk=extra.journal_line_id))
    seen = set()
    for jl in group:
        if jl.pk in seen:
            continue
        seen.add(jl.pk)
        _release_group(jl)
        cleared["ledger_lines"] += 1
    if not cleared["payments"] and not cleared["ledger_lines"] and bank_line.match_status != status.MATCHED:
        raise BusinessRuleError("This line is not matched.")
    bank_line.match_status = status.UNMATCHED
    bank_line.updated_by = user
    bank_line.save(update_fields=["match_status", "updated_by", "updated_at"])
    _audit(company, user, "DELETE", "BankStatementLine", bank_line.pk, f"unmatched bank statement line {bank_line.pk}")
    for session in BankReconSession.objects.filter(statement_id=bank_line.statement_id).exclude(
        status=BankReconSession.Status.FINALISED
    ):
        refresh_status(session)
    return cleared


# --------------------------------------------------------------------- the reconciliation figures
def statement_date_for(session: BankReconSession) -> date:
    if session.statement_date:
        return session.statement_date
    if session.statement.period_end:
        return session.statement.period_end
    last = session.statement.lines.order_by("-txn_date").values_list("txn_date", flat=True).first()
    return last or timezone.localdate()


def closing_balance_for(session: BankReconSession):
    """Entered figure first, else the bank's own running balance on the last line, else unknown."""
    if session.statement_closing_balance is not None:
        return _q(session.statement_closing_balance)
    last = session.statement.lines.exclude(balance_after__isnull=True).order_by("-txn_date", "-id").first()
    return _q(last.balance_after) if last is not None else None


def session_summary(session: BankReconSession) -> dict:
    as_at = statement_date_for(session)
    closing = closing_balance_for(session)
    base = JournalLine.objects.filter(company=session.company, account=session.account, entry__status__in=STATUSES_IN_BOOKS)
    gl = base.filter(entry__entry_date__lte=as_at).aggregate(d=Sum("debit"), c=Sum("credit"))
    gl_balance = _q(gl["d"]) - _q(gl["c"])
    outstanding = base.filter(
        entry__entry_date__lte=as_at, bank_statement_line__isnull=True, reconciled_at__isnull=True
    ).aggregate(d=Sum("debit"), c=Sum("credit"))
    deposits, payments = _q(outstanding["d"]), _q(outstanding["c"])
    reconciled = base.filter(bank_statement_line__statement=session.statement).aggregate(d=Sum("debit"), c=Sum("credit"))
    reconciled_total = _q(reconciled["d"]) - _q(reconciled["c"])
    BankLineMatchStatus, _line, _match = _models()
    lines = session.statement.lines
    open_lines = lines.filter(match_status__in=[BankLineMatchStatus.UNMATCHED, BankLineMatchStatus.SUGGESTED])
    unrecorded = _q(open_lines.aggregate(s=Sum("amount"))["s"])
    adjusted_bank = None if closing is None else closing + deposits - payments
    adjusted_book = gl_balance + unrecorded
    difference = None if adjusted_bank is None else adjusted_bank - adjusted_book
    return {
        "statement_date": as_at.isoformat(),
        "statement_closing_balance": None if closing is None else str(closing),
        "gl_balance_as_at": str(gl_balance),
        "reconciled_total": str(reconciled_total),
        "outstanding_deposits": str(deposits),
        "outstanding_payments": str(payments),
        "unrecorded_bank_items": str(unrecorded),
        "adjusted_bank_balance": None if adjusted_bank is None else str(adjusted_bank),
        "adjusted_book_balance": str(adjusted_book),
        "difference": None if difference is None else str(difference),
        "statement_lines": lines.count(),
        "matched_lines": lines.filter(match_status=BankLineMatchStatus.MATCHED).count(),
        "open_lines": open_lines.count(),
    }


def refresh_status(session: BankReconSession) -> BankReconSession:
    """OPEN -> IN_PROGRESS -> RECONCILED follows the matches. FINALISED is only left by reopening."""
    if session.status in (BankReconSession.Status.FINALISED, BankReconSession.Status.CLOSED):
        return session
    summary = session_summary(session)
    matched = summary["matched_lines"] > 0
    if matched and summary["difference"] is not None and Decimal(summary["difference"]) == 0 and summary["open_lines"] == 0:
        new = BankReconSession.Status.RECONCILED
    elif matched:
        new = BankReconSession.Status.IN_PROGRESS
    else:
        new = BankReconSession.Status.OPEN
    fields = []
    diff = None if summary["difference"] is None else _q(summary["difference"])
    if session.last_difference != diff:
        session.last_difference = diff
        fields.append("last_difference")
    if session.status != new:
        session.status = new
        fields.append("status")
    gl = _q(summary["gl_balance_as_at"])
    if session.gl_balance != gl:
        session.gl_balance = gl
        fields.append("gl_balance")
    if summary["statement_closing_balance"] is not None and session.statement_balance != _q(summary["statement_closing_balance"]):
        session.statement_balance = _q(summary["statement_closing_balance"])
        fields.append("statement_balance")
    if fields:
        session.save(update_fields=[*fields, "updated_at"])
    return session


# --------------------------------------------------------------------- finalise / reopen
def write_off_limit() -> Decimal:
    return _q(getattr(settings, "RECON_WRITE_OFF_LIMIT", "10.00"))


@transaction.atomic
def finalise(session_id: int, company, user, *, write_off: bool = False, is_owner: bool = False) -> BankReconSession:
    from .services import PostingService

    session = BankReconSession.objects.select_for_update().get(pk=session_id, company=company)
    if session.status == BankReconSession.Status.FINALISED:
        raise BusinessRuleError("This reconciliation is already finalised.", code="recon_finalised")
    summary = session_summary(session)
    if summary["difference"] is None:
        raise BusinessRuleError(
            "Enter the statement closing balance before finalising.", code="recon_closing_balance_missing"
        )
    difference = _q(summary["difference"])
    if summary["open_lines"]:
        raise BusinessRuleError(
            f"{summary['open_lines']} statement line(s) are still unmatched. Match, create an entry, or ignore them.",
            code="recon_open_lines",
        )
    if difference != 0:
        if not write_off:
            raise BusinessRuleError(
                f"The difference is {difference}. It must be zero to finalise.", code="recon_difference",
            )
        if not is_owner:
            raise BusinessRuleError("Only an owner can write off a difference.", code="recon_write_off_owner")
        if abs(difference) > write_off_limit():
            raise BusinessRuleError(
                f"A difference above {write_off_limit()} cannot be written off. Find the cause first.",
                code="recon_write_off_limit",
            )
        charges = PostingService._account(company, "5200")
        amount = abs(difference)
        # difference > 0: the bank holds more than the books, so the books go up.
        lines = (
            [{"account": session.account, "debit": amount}, {"account": charges, "credit": amount}]
            if difference > 0
            else [{"account": charges, "debit": amount}, {"account": session.account, "credit": amount}]
        )
        entry = PostingService.post(
            company=company, source_type="BANK_RECON_WRITE_OFF", source_id=session.pk, purpose="CREATE",
            entry_date=date.fromisoformat(summary["statement_date"]), user=user,
            narration=f"Bank reconciliation difference written off (session {session.pk})", lines=lines,
        )
        if entry is not None:
            # Counted in the ledger balance, so it must leave the outstanding items.
            entry.lines.filter(account=session.account).update(reconciled_at=timezone.now())
            session.write_off_entry = entry
    session.status = BankReconSession.Status.FINALISED
    session.finalised_at = timezone.now()
    session.finalised_by = user
    session.updated_by = user
    session.save()
    _audit(company, user, "UPDATE", "BankReconSession", session.pk, f"finalised; difference {difference}")
    return session


@transaction.atomic
def reopen(session_id: int, company, user, reason: str) -> BankReconSession:
    reason = (reason or "").strip()
    if not reason:
        raise BusinessRuleError("Give a reason for reopening.", code="reason_required")
    session = BankReconSession.objects.select_for_update().get(pk=session_id, company=company)
    if session.status != BankReconSession.Status.FINALISED:
        raise BusinessRuleError("Only a finalised reconciliation can be reopened.")
    session.status = BankReconSession.Status.IN_PROGRESS
    session.reopen_reason = reason[:255]
    session.updated_by = user
    session.save(update_fields=["status", "reopen_reason", "updated_by", "updated_at"])
    _audit(company, user, "UPDATE", "BankReconSession", session.pk, f"reopened: {reason}")
    return refresh_status(session)


# --------------------------------------------------------------------- suggestions
_TOKEN = re.compile(r"[a-z0-9]{4,}")


def _tokens(*parts) -> set[str]:
    return set(_TOKEN.findall(" ".join(str(p or "") for p in parts).lower()))


def suggestions(session: BankReconSession, *, window_days: int = 5, limit: int = 300) -> list[dict]:
    """Propose ledger-to-statement matches: same signed amount, close in date, shared words add confidence."""
    BankLineMatchStatus, _line, _match = _models()
    bank_lines = list(
        session.statement.lines.filter(match_status=BankLineMatchStatus.UNMATCHED).order_by("txn_date", "id")[:limit]
    )
    if not bank_lines:
        return []
    as_at = statement_date_for(session)
    ledger = list(
        JournalLine.objects.filter(
            company=session.company, account=session.account, entry__status=JournalEntry.Status.POSTED,
            bank_statement_line__isnull=True, reconciled_at__isnull=True,
            entry__entry_date__lte=as_at + timedelta(days=window_days),
        )
        .select_related("entry")
        .order_by("entry__entry_date", "id")
    )
    by_amount: dict[Decimal, list[JournalLine]] = {}
    for jl in ledger:
        by_amount.setdefault(_signed(jl), []).append(jl)
    rows = []
    claimed: dict[int, int] = {}
    for bl in bank_lines:
        cands = []
        for jl in by_amount.get(_q(bl.amount), []):
            gap = abs((jl.entry.entry_date - bl.txn_date).days)
            if gap > window_days:
                continue
            shared = _tokens(bl.narration, bl.utr) & _tokens(jl.entry.narration, jl.entry.number, jl.narration)
            score = 60 + (20 if gap == 0 else 10 if gap <= 2 else 0) + min(20, 10 * len(shared))
            cands.append((score, gap, jl, sorted(shared)))
        cands.sort(key=lambda c: (-c[0], c[1], c[2].pk))
        for score, gap, jl, shared in cands[:3]:
            rows.append({
                "bank_line": bl.pk, "journal_line": jl.pk, "score": score, "date_gap": gap, "shared_words": shared,
                "amount": str(_q(bl.amount)),
            })
            claimed[jl.pk] = claimed.get(jl.pk, 0) + 1
    per_bank = _count_by(rows, "bank_line")
    for r in rows:
        unique = per_bank[r["bank_line"]] == 1 and claimed.get(r["journal_line"], 0) == 1
        r["confidence"] = "high" if (r["score"] >= 80 and unique) else "medium" if r["score"] >= 70 else "low"
    return rows


def _count_by(rows, key):
    out: dict = {}
    for r in rows:
        out[r[key]] = out.get(r[key], 0) + 1
    return out


def accept_suggestions(company, user, session: BankReconSession, pairs) -> dict:
    done, failed = 0, []
    for pair in pairs:
        try:
            with transaction.atomic():
                match_gl(company, user, session, [pair["journal_line"]], [pair["bank_line"]])
            done += 1
        except BusinessRuleError as exc:
            failed.append({"bank_line": pair.get("bank_line"), "journal_line": pair.get("journal_line"), "reason": str(exc.detail)})
    return {"matched": done, "failed": failed}


# --------------------------------------------------------------------- create entry from a statement line
CONTROL_REFUSED = {"1200", "2100", "2300", "1250"}


@transaction.atomic
def create_entry_from_line(company, user, session: BankReconSession, bank_line_id, account_id, *, narration="", entry_date=None) -> dict:
    """Book a bank item that has no entry (a charge, interest, an unrecorded receipt) and match it."""
    from .services import PostingService

    _s, BankStatementLine, _m = _models()
    if session.status == BankReconSession.Status.FINALISED:
        raise BusinessRuleError("This reconciliation is finalised. Reopen it to change matches.", code="recon_finalised")
    bank_line = BankStatementLine.objects.select_for_update().filter(
        company=company, pk=bank_line_id, statement=session.statement
    ).first()
    if bank_line is None:
        raise BusinessRuleError("Statement line not found on this reconciliation.")
    assert_line_free(bank_line, engine="gl")
    account = Account.objects.filter(company=company, pk=account_id, is_active=True).first()
    if account is None:
        raise BusinessRuleError("Choose an active account for the other side of the entry.")
    if account.pk == session.account_id:
        raise BusinessRuleError("The other side cannot be the bank ledger itself.")
    if account.code in CONTROL_REFUSED:
        raise BusinessRuleError(
            "Customer and supplier money is recorded as a receipt or payment so it reaches their balance. "
            "Use the payments reconciliation for it.",
            code="recon_party_account",
        )
    amount = _q(abs(bank_line.amount))
    money_in = bank_line.amount > 0
    lines = (
        [{"account": session.account, "debit": amount}, {"account": account, "credit": amount}]
        if money_in
        else [{"account": account, "debit": amount}, {"account": session.account, "credit": amount}]
    )
    entry = PostingService.post(
        company=company, source_type="BANK_LINE_ENTRY", source_id=bank_line.pk, purpose="CREATE",
        entry_date=entry_date or bank_line.txn_date, user=user,
        narration=(narration or bank_line.narration or "Bank statement item")[:240], lines=lines,
    )
    if entry is None:
        raise BusinessRuleError("An entry for this statement line already exists.")
    jl = entry.lines.get(account=session.account)
    match_gl(company, user, session, [jl.pk], [bank_line.pk])
    return {"journal_entry": entry.pk, "number": entry.number}


# --------------------------------------------------------------------- reports
def reconciliation_report(session: BankReconSession) -> dict:
    summary = session_summary(session)
    BankLineMatchStatus, _l, _m = _models()
    as_at = date.fromisoformat(summary["statement_date"])
    outstanding = (
        JournalLine.objects.filter(
            company=session.company, account=session.account, entry__status__in=STATUSES_IN_BOOKS,
            entry__entry_date__lte=as_at, bank_statement_line__isnull=True, reconciled_at__isnull=True,
        )
        .select_related("entry")
        .order_by("entry__entry_date", "id")
    )
    unrecorded = session.statement.lines.filter(
        match_status__in=[BankLineMatchStatus.UNMATCHED, BankLineMatchStatus.SUGGESTED]
    ).order_by("txn_date", "id")
    return {
        "session": session.pk,
        "bank": session.account.name,
        "status": session.status,
        "summary": summary,
        "outstanding_items": [
            {"date": j.entry.entry_date.isoformat(), "number": j.entry.number, "narration": j.entry.narration,
             "amount": str(_signed(j))}
            for j in outstanding
        ],
        "unrecorded_items": [
            {"date": b.txn_date.isoformat(), "narration": b.narration, "amount": str(_q(b.amount))} for b in unrecorded
        ],
        "finalised_at": session.finalised_at.isoformat() if session.finalised_at else None,
        "finalised_by": getattr(session.finalised_by, "email", "") if session.finalised_by_id else "",
    }


def report_xlsx(session: BankReconSession) -> bytes:
    from openpyxl import Workbook

    data = reconciliation_report(session)
    s = data["summary"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Reconciliation"
    ws.append([f"Bank reconciliation: {data['bank']}"])
    ws.append(["As at", s["statement_date"]])
    ws.append(["Status", data["status"]])
    ws.append([])
    for label, key in (
        ("Balance per bank statement", "statement_closing_balance"),
        ("Add: deposits not yet cleared", "outstanding_deposits"),
        ("Less: payments not yet cleared", "outstanding_payments"),
        ("Adjusted bank balance", "adjusted_bank_balance"),
        ("Balance per books", "gl_balance_as_at"),
        ("Add/less: bank items not in books", "unrecorded_bank_items"),
        ("Adjusted book balance", "adjusted_book_balance"),
        ("Difference", "difference"),
    ):
        ws.append([label, s[key]])
    ws.append([])
    ws.append(["Outstanding in books"])
    ws.append(["Date", "Voucher", "Narration", "Amount"])
    for r in data["outstanding_items"]:
        ws.append([r["date"], r["number"], r["narration"], r["amount"]])
    ws.append([])
    ws.append(["On the statement, not in books"])
    ws.append(["Date", "Narration", "Amount"])
    for r in data["unrecorded_items"]:
        ws.append([r["date"], r["narration"], r["amount"]])
    ws.append([])
    ws.append(["Finalised by", data["finalised_by"], data["finalised_at"] or ""])
    ws.append(["Prepared by", "", "Reviewed by", ""])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def report_pdf(session: BankReconSession) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    data = reconciliation_report(session)
    s = data["summary"]
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    y = [285 * mm]

    def line(text, bold=False):
        if y[0] < 20 * mm:
            pdf.showPage()
            y[0] = 285 * mm
        pdf.setFont("Helvetica-Bold" if bold else "Helvetica", 10)
        pdf.drawString(20 * mm, y[0], text[:110])
        y[0] -= 6 * mm

    line(f"Bank reconciliation: {data['bank']}", True)
    line(f"As at {s['statement_date']}   Status {data['status']}")
    y[0] -= 3 * mm
    for label, key in (
        ("Balance per bank statement", "statement_closing_balance"),
        ("Add: deposits not yet cleared", "outstanding_deposits"),
        ("Less: payments not yet cleared", "outstanding_payments"),
        ("Adjusted bank balance", "adjusted_bank_balance"),
        ("Balance per books", "gl_balance_as_at"),
        ("Add/less: bank items not in books", "unrecorded_bank_items"),
        ("Adjusted book balance", "adjusted_book_balance"),
        ("Difference", "difference"),
    ):
        line(f"{label}: {s[key]}", key in ("adjusted_bank_balance", "adjusted_book_balance", "difference"))
    y[0] -= 3 * mm
    line("Outstanding in books", True)
    for r in data["outstanding_items"]:
        line(f"{r['date']}  {r['number']}  {r['narration'][:50]}  {r['amount']}")
    y[0] -= 3 * mm
    line("On the statement, not in books", True)
    for r in data["unrecorded_items"]:
        line(f"{r['date']}  {r['narration'][:60]}  {r['amount']}")
    y[0] -= 6 * mm
    line(f"Finalised by: {data['finalised_by'] or '-'}  {data['finalised_at'] or ''}")
    line("Prepared by: ______________    Reviewed by: ______________")
    pdf.showPage()
    pdf.save()
    return buf.getvalue()


# --------------------------------------------------------------------- repair
def inconsistent_lines(company) -> list[dict]:
    """Statement lines whose match state disagrees with the rows that should back it."""
    BankLineMatchStatus, BankStatementLine, ReconMatch = _models()
    found = []
    gl_linked = set(JournalLine.objects.filter(company=company, bank_statement_line__isnull=False).values_list("bank_statement_line_id", flat=True))
    gl_linked |= set(JournalLineBankLink.objects.filter(company=company).values_list("bank_line_id", flat=True))
    pay_linked = set(ReconMatch.objects.filter(company=company).values_list("line_id", flat=True))
    for bl in BankStatementLine.objects.filter(company=company).filter(
        Q(match_status=BankLineMatchStatus.MATCHED) | Q(pk__in=gl_linked) | Q(pk__in=pay_linked)
    ):
        in_gl, in_pay = bl.pk in gl_linked, bl.pk in pay_linked
        matched = bl.match_status == BankLineMatchStatus.MATCHED
        if in_gl and in_pay:
            found.append({"line": bl.pk, "problem": "matched_in_both", "fix": "manual"})
        elif (in_gl or in_pay) and not matched:
            found.append({"line": bl.pk, "problem": "linked_but_not_marked_matched", "fix": "mark_matched"})
        elif matched and not in_gl and not in_pay:
            found.append({"line": bl.pk, "problem": "marked_matched_without_match", "fix": "mark_unmatched"})
    return found


def repair(company, user=None, *, prefer: str | None = None) -> dict:
    """Fix what is unambiguous; ``prefer`` ('gl' or 'payments') also settles lines matched in both."""
    BankLineMatchStatus, BankStatementLine, ReconMatch = _models()
    fixed = {"mark_matched": 0, "mark_unmatched": 0, "resolved_both": 0, "left_for_review": 0}
    for item in inconsistent_lines(company):
        bl = BankStatementLine.objects.get(pk=item["line"])
        if item["fix"] == "mark_matched":
            bl.match_status = BankLineMatchStatus.MATCHED
            bl.save(update_fields=["match_status", "updated_at"])
            fixed["mark_matched"] += 1
        elif item["fix"] == "mark_unmatched":
            bl.match_status = BankLineMatchStatus.UNMATCHED
            bl.save(update_fields=["match_status", "updated_at"])
            fixed["mark_unmatched"] += 1
        elif prefer in ("gl", "payments"):
            if prefer == "gl":
                ReconMatch.objects.filter(line=bl).delete()
            else:
                for jl in JournalLine.objects.filter(bank_statement_line=bl):
                    _release_group(jl)
                JournalLineBankLink.objects.filter(bank_line=bl).delete()
            fixed["resolved_both"] += 1
        else:
            fixed["left_for_review"] += 1
    return fixed


def _audit(company, user, action, entity, entity_id, description) -> None:
    from core.services.audit import AuditService

    AuditService.log(
        company=company, user=user, action=action, entity_type=entity, entity_id=entity_id, description=description[:240],
    )
