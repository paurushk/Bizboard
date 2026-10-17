"""ACS-15: expenses post to the ledger.

An expense dated on or after ``Company.expense_gl_start_date`` carries a journal entry:
``Dr <expense ledger> / Cr Cash (1100) or the bank's own ledger``. Editing an expense
reverses the old entry and posts the new one; voiding reverses it. Before the start date
(or with the date empty) an expense stays a register row, exactly as before.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from core.exceptions import BusinessRuleError

from .models import Account, Expense, ExpenseCategoryAccount, JournalEntry
from .services import PostingService

SOURCE_TYPE = "EXPENSE"
PURPOSE = "CREATE"
DEFAULT_EXPENSE_CODE = "5000"


def posting_active(company, expense_date: date | None) -> bool:
    start = getattr(company, "expense_gl_start_date", None)
    return bool(
        getattr(company, "accounting_enabled", False)
        and start
        and expense_date
        and expense_date >= start
    )


def resolve_expense_account(company, expense: Expense) -> Account:
    """The ledger an expense hits: its own choice, else its category's mapping, else 5000."""
    if expense.expense_account_id:
        return expense.expense_account
    mapping = (
        ExpenseCategoryAccount.objects.filter(company=company, category_id=expense.category_id)
        .select_related("account")
        .first()
    )
    if mapping is not None and mapping.account.is_active:
        return mapping.account
    return PostingService._account(company, DEFAULT_EXPENSE_CODE)


def _credit_account(company, expense: Expense) -> Account:
    if expense.payment_mode == Expense.PaymentMode.BANK:
        if expense.bank_account_id is None:
            raise BusinessRuleError("Choose the bank account this expense was paid from.")
        return PostingService._bank_gl_account(company, expense.bank_account, expense.expense_date)
    return PostingService._account(company, "1100")


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def expected_lines(company, expense: Expense) -> list[dict]:
    """Dr expense (and input tax when claimed) / Cr cash or bank (and TDS payable when deducted).

    ``amount`` is what the expense cost in total. Tax is only split out when the expense is
    marked ITC-eligible; otherwise it stays in the expense. TDS reduces the cash paid.
    """
    amount = _money(expense.amount)
    cgst, sgst, igst = _money(expense.cgst_amount), _money(expense.sgst_amount), _money(expense.igst_amount)
    tds = _money(expense.tds_amount)
    claimed = (cgst + sgst + igst) if expense.itc_eligible else Decimal("0.00")
    cost_center = expense.cost_center if expense.cost_center_id else None

    def line(account, side, value):
        row = {"account": account, side: value}
        if cost_center is not None and side == "debit" and account.type == Account.Type.EXPENSE:
            row["cost_center"] = cost_center
        return row

    lines = [line(resolve_expense_account(company, expense), "debit", amount - claimed)]
    if expense.itc_eligible:
        for code, part in (("1310", cgst), ("1320", sgst), ("1330", igst)):
            if part > 0:
                lines.append({"account": PostingService._account(company, code), "debit": part})
    lines.append({"account": _credit_account(company, expense), "credit": amount - tds})
    if tds > 0:
        lines.append({"account": PostingService._account(company, "2265"), "credit": tds})
    return lines


def _signature(lines) -> set[tuple[int, Decimal, Decimal, int]]:
    sig = set()
    for line in lines:
        account = line["account"] if isinstance(line, dict) else line.account
        debit = Decimal(str((line.get("debit") if isinstance(line, dict) else line.debit) or 0)).quantize(Decimal("0.01"))
        credit = Decimal(str((line.get("credit") if isinstance(line, dict) else line.credit) or 0)).quantize(Decimal("0.01"))
        cc = line.get("cost_center") if isinstance(line, dict) else line.cost_center
        sig.add((account.id, debit, credit, getattr(cc, "pk", 0) or 0))
    return sig


def _entry_matches(entry: JournalEntry, expense: Expense, lines: list[dict]) -> bool:
    return entry.entry_date == expense.expense_date and _signature(entry.lines.all()) == _signature(lines)


@transaction.atomic
def sync_expense_posting(expense: Expense, user=None) -> JournalEntry | None:
    """Make the ledger agree with the expense. Safe to call after any create, edit or void."""
    company = expense.company
    entry = expense.journal_entry if expense.journal_entry_id else None
    if entry is not None and entry.status != JournalEntry.Status.POSTED:
        entry = None
    wanted = expense.status == Expense.Status.ACTIVE and posting_active(company, expense.expense_date)
    lines = None
    if wanted:
        PostingService._ensure_chart(company)
        lines = expected_lines(company, expense)
        if entry is not None and _entry_matches(entry, expense, lines):
            return entry
    if entry is not None:
        # The old entry goes back on its own date; the replacement is posted on the new one.
        PostingService.reverse(entry, user, entry_date=entry.entry_date)
        expense.journal_entry = None
        expense.save(update_fields=["journal_entry"])
    if not wanted:
        return None
    posted = PostingService.post(
        company=company,
        source_type=SOURCE_TYPE,
        source_id=expense.id,
        purpose=PURPOSE,
        entry_date=expense.expense_date,
        user=user,
        narration=f"Expense {expense.number}" + (f": {expense.party_name}" if expense.party_name else ""),
        lines=lines,
    )
    if posted is not None:
        expense.journal_entry = posted
        expense.save(update_fields=["journal_entry"])
    return posted


def pending_expenses(company, *, up_to: date | None = None):
    """Active expenses that should be in the books but are not."""
    start = getattr(company, "expense_gl_start_date", None)
    if not (getattr(company, "accounting_enabled", False) and start):
        return Expense.objects.none()
    qs = Expense.objects.filter(
        company=company, status=Expense.Status.ACTIVE, journal_entry__isnull=True, expense_date__gte=start,
    )
    if up_to is not None:
        qs = qs.filter(expense_date__lte=up_to)
    return qs.select_related("category", "bank_account", "expense_account").order_by("expense_date", "id")


def pending_summary(company) -> dict:
    qs = pending_expenses(company)
    agg = qs.aggregate(total=Sum("amount"))
    return {"count": qs.count(), "total": agg["total"] or Decimal("0")}


def post_pending_expenses(company, user=None, *, dry_run: bool = False) -> dict:
    """Post every pending expense. A closed month or a bad row is reported, not fatal."""
    posted, skipped = 0, []
    total = Decimal("0")
    for expense in pending_expenses(company):
        if dry_run:
            posted += 1
            total += expense.amount
            continue
        try:
            with transaction.atomic():
                if sync_expense_posting(expense, user) is not None:
                    posted += 1
                    total += expense.amount
        except BusinessRuleError as exc:
            skipped.append({"id": expense.id, "number": expense.number, "reason": str(exc.detail)})
    return {"posted": posted, "total": total, "skipped": skipped, "dry_run": dry_run}
