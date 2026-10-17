"""ACS-60: the ledger Day Book.

Every journal line posted in a date range, company-wide, grouped the way an accountant reads a day:
voucher, account, party, debit, credit. The totals must tie to the trial-balance movement for the
same dates; the screen shows that check. The old cash-position view lives on as the "daily cash summary".
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q, Sum

from accounting.journal_sources import source_label, source_path
from accounting.models import JournalEntry, JournalLine
from core.exceptions import BusinessRuleError

MAX_RANGE_DAYS = 31

# voucher type -> (label, source types, optional purpose prefix)
VOUCHER_TYPES: dict[str, tuple[str, tuple[str, ...], str]] = {
    "SALES": ("Sales", ("SALES_INVOICE",), ""),
    "SALES_ADJUSTMENT": ("Sales return / note", ("SALES_RETURN", "SALES_CREDIT_NOTE", "SALES_DEBIT_NOTE", "POS_REFUND"), ""),
    "PURCHASE": ("Purchase", ("PURCHASE_INVOICE", "BILL_OF_ENTRY"), ""),
    "PURCHASE_ADJUSTMENT": ("Purchase return / note", ("PURCHASE_RETURN", "PURCHASE_CREDIT_NOTE", "PURCHASE_DEBIT_NOTE"), ""),
    "RECEIPT": ("Receipt", ("CUSTOMER_RECEIPT", "CHEQUE_DISHONOUR"), ""),
    "PAYMENT": ("Payment", ("SUPPLIER_PAYMENT", "PAYMENT_ALLOCATION", "CUSTOMER_ADVANCE_REFUND"), ""),
    "EXPENSE": ("Expense", ("EXPENSE",), ""),
    "DEPRECIATION": ("Depreciation", ("FIXED_ASSET",), "DEPRECIATION-"),
    "FIXED_ASSET": ("Fixed asset", ("FIXED_ASSET",), ""),
    "PAYROLL": ("Payroll", ("PAY_RUN",), ""),
    "STOCK": ("Stock / production", ("STOCK_MOVEMENT", "WORK_ORDER"), ""),
    "BANK": ("Bank entry", ("BANK_LINE_ENTRY", "BANK_RECON_WRITE_OFF"), ""),
    "YEAR_END": ("Year-end close", ("FY_CLOSE",), ""),
    "JOURNAL": ("Journal", ("MANUAL_JOURNAL", "JOURNAL_REVERSAL"), ""),
}


def voucher_type_of(source_type: str, purpose: str) -> str:
    for key in ("DEPRECIATION",):
        label, sources, prefix = VOUCHER_TYPES[key]
        if source_type in sources and (purpose or "").startswith(prefix):
            return key
    for key, (_label, sources, prefix) in VOUCHER_TYPES.items():
        if key in ("DEPRECIATION",):
            continue
        if source_type in sources and not prefix:
            return key
    return "OTHER"


def voucher_label(key: str) -> str:
    return VOUCHER_TYPES.get(key, ("Other",))[0]


def _type_filter(key: str) -> Q:
    if key == "OTHER":
        known = {s for _l, sources, _p in VOUCHER_TYPES.values() for s in sources}
        return ~Q(entry__source_type__in=known)
    if key not in VOUCHER_TYPES:
        raise BusinessRuleError("Unknown voucher type.")
    _label, sources, prefix = VOUCHER_TYPES[key]
    q = Q(entry__source_type__in=sources)
    if key == "DEPRECIATION":
        q &= Q(entry__purpose__startswith=prefix)
    elif key == "FIXED_ASSET":
        q &= ~Q(entry__purpose__startswith="DEPRECIATION-")
    return q


def parse_range(raw_from, raw_to, today: date) -> tuple[date, date]:
    def one(raw, name):
        if not raw:
            return None
        try:
            return date.fromisoformat(str(raw).strip()[:10])
        except ValueError as exc:
            raise BusinessRuleError(f"{name} must be a date like 2026-04-01.", code="bad_date") from exc

    start, end = one(raw_from, "date_from"), one(raw_to, "date_to")
    start = start or end or today
    end = end or start
    if end < start:
        raise BusinessRuleError("The end date cannot be before the start date.", code="bad_range")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise BusinessRuleError(f"Choose a range of at most {MAX_RANGE_DAYS} days.", code="range_too_long")
    return start, end


def base_queryset(company, start: date, end: date, params):
    qs = JournalLine.objects.filter(
        company=company,
        entry__status__in=[JournalEntry.Status.POSTED, JournalEntry.Status.REVERSED],
        entry__entry_date__gte=start,
        entry__entry_date__lte=end,
    ).select_related("entry", "account", "customer", "supplier", "cost_center")
    if params.get("voucher_type"):
        qs = qs.filter(_type_filter(params["voucher_type"].upper()))
    if params.get("account"):
        qs = qs.filter(account_id=params["account"])
    if params.get("cost_center"):
        qs = qs.filter(cost_center_id=params["cost_center"])
    if params.get("customer"):
        qs = qs.filter(customer_id=params["customer"])
    if params.get("supplier"):
        qs = qs.filter(supplier_id=params["supplier"])
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(entry__number__icontains=q) | Q(entry__narration__icontains=q) | Q(narration__icontains=q)
            | Q(account__name__icontains=q) | Q(customer__name__icontains=q) | Q(supplier__name__icontains=q)
        )
    return qs.order_by("entry__entry_date", "entry_id", "id")


def row_of(line: JournalLine) -> dict:
    entry = line.entry
    key = voucher_type_of(entry.source_type, entry.purpose)
    party = line.customer.name if line.customer_id else (line.supplier.name if line.supplier_id else "")
    return {
        "id": line.pk,
        "date": entry.entry_date.isoformat(),
        "voucher": entry.number,
        "entry_id": entry.pk,
        "voucher_type": key,
        "voucher_type_label": voucher_label(key),
        "account_code": line.account.code,
        "account_name": line.account.name,
        "party": party,
        "cost_center": line.cost_center.name if line.cost_center_id else "",
        "debit": str(line.debit or Decimal("0")),
        "credit": str(line.credit or Decimal("0")),
        "narration": line.narration or entry.narration,
        "status": entry.status,
        "source_label": source_label(entry.source_type) if entry.source_type else "",
        "source_path": source_path(entry.source_type, entry.source_id),
    }


def totals(qs) -> dict:
    agg = qs.aggregate(d=Sum("debit"), c=Sum("credit"))
    debit, credit = agg["d"] or Decimal("0"), agg["c"] or Decimal("0")
    return {"debit": str(debit), "credit": str(credit), "balanced": debit == credit}


def per_day_balance(qs) -> list[dict]:
    """Debit and credit for each day of the unfiltered range; a day that does not balance is flagged."""
    rows = qs.values("entry__entry_date").annotate(d=Sum("debit"), c=Sum("credit")).order_by("entry__entry_date")
    return [
        {"date": r["entry__entry_date"].isoformat(), "debit": str(r["d"] or 0), "credit": str(r["c"] or 0),
         "balanced": (r["d"] or 0) == (r["c"] or 0)}
        for r in rows
    ]


def tie_out(company, start: date, end: date, ledger_debit: Decimal, ledger_credit: Decimal) -> dict:
    """The same dates read through the trial balance's own query must give the same totals."""
    from accounting.reports import _balances

    rows = _balances(company, date_from=start, date_to=end)
    tb_debit = sum((r["debit"] for r in rows), Decimal("0"))
    tb_credit = sum((r["credit"] for r in rows), Decimal("0"))
    return {
        "trial_balance_debit": str(tb_debit),
        "trial_balance_credit": str(tb_credit),
        "ties": tb_debit == ledger_debit and tb_credit == ledger_credit,
    }


def available_types(company, start: date, end: date) -> list[dict]:
    seen = {}
    for st, purpose in (
        JournalEntry.objects.filter(
            company=company, status__in=[JournalEntry.Status.POSTED, JournalEntry.Status.REVERSED],
            entry_date__gte=start, entry_date__lte=end,
        ).values_list("source_type", "purpose").distinct()
    ):
        key = voucher_type_of(st, purpose)
        seen[key] = voucher_label(key)
    return [{"key": k, "label": v} for k, v in sorted(seen.items(), key=lambda kv: kv[1])]


def neighbours(day: date) -> dict:
    return {"previous": (day - timedelta(days=1)).isoformat(), "next": (day + timedelta(days=1)).isoformat()}
