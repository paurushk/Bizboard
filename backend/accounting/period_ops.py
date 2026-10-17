"""ACS-30..34: period close readiness, reopen, year generation, FY-close preview and reversal."""
from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.exceptions import BusinessRuleError

from .models import Account, AccountingPeriod, JournalEntry, JournalLine
from .services import BooksHealthService

# Where an accountant goes to fix each blocker (front-end route + short title).
FIX_PATHS = {
    "AR_CONTROL_MISMATCH": ("/reports/books-health", "Receivables control does not match customer balances"),
    "AP_CONTROL_MISMATCH": ("/reports/books-health", "Payables control does not match supplier balances"),
    "DOCUMENT_MISSING_POSTING": ("/reports/books-health", "Completed documents are missing from the books"),
    "DOCS_GL_AR_MISMATCH": ("/reports/books-health", "Receivable documents and ledger disagree"),
    "DOCS_GL_AP_MISMATCH": ("/reports/books-health", "Payable documents and ledger disagree"),
    "EXPENSE_MISSING_POSTING": ("/accounting/expenses", "Expenses are not posted to the books"),
    "OPEN_WIP": ("/manufacturing/work-orders", "Released work orders are still open"),
    "DEPRECIATION_FAILED": ("/accounting/fixed-assets", "Depreciation failed for some assets"),
}


def period_label(period: AccountingPeriod) -> str:
    return f"{period.start_date.year:04d}-{period.start_date.month:02d}"


def _gst_status(company, period: AccountingPeriod) -> str:
    from reporting.models import GstReturnPeriod

    row = GstReturnPeriod.objects.filter(company=company, period=period_label(period)).first()
    return row.status if row is not None else GstReturnPeriod.Status.OPEN


def earlier_open_period(company, period: AccountingPeriod):
    return (
        AccountingPeriod.objects.filter(
            company=company, end_date__lt=period.start_date, status=AccountingPeriod.Status.OPEN,
        )
        .order_by("start_date")
        .first()
    )


def decorate_blocker(blocker: dict) -> dict:
    code = blocker.get("code", "")
    path, title = FIX_PATHS.get(code, ("/reports/books-health", blocker.get("message", code)))
    out = {
        "code": code,
        "severity": blocker.get("severity", "error"),
        "message": blocker.get("message") or title,
        "title": title,
        "fix_path": path,
    }
    for key in ("count", "amount"):
        if key in blocker:
            out[key] = blocker[key]
    return out


def close_readiness(company, period: AccountingPeriod, *, with_blockers: bool = True) -> dict:
    """Why this month can or cannot close, ordered so the first item is the first thing to fix."""
    earlier = earlier_open_period(company, period)
    blockers = []
    if with_blockers and period.status != AccountingPeriod.Status.CLOSED and earlier is None:
        blockers = [
            decorate_blocker(b)
            for b in BooksHealthService.period_close_blockers(company, period=period_label(period))
        ]
    advisory = []
    unreconciled = JournalLine.objects.filter(
        company=company,
        account__code__startswith="1500",
        entry__status=JournalEntry.Status.POSTED,
        entry__entry_date__gte=period.start_date,
        entry__entry_date__lte=period.end_date,
        bank_statement_line__isnull=True,
        reconciled_at__isnull=True,
    ).count()
    if unreconciled:
        advisory.append({
            "code": "UNRECONCILED_BANK_LINES",
            "severity": "info",
            "message": f"{unreconciled} bank ledger line(s) in this month are not reconciled yet.",
            "title": "Bank lines not reconciled",
            "fix_path": "/accounting/bank-reconciliation",
            "count": unreconciled,
        })
    not_closed = period.status != AccountingPeriod.Status.CLOSED
    free = earlier is None and not blockers
    return {
        "period": period.id,
        "name": period.name,
        "status": period.status,
        "gst_status": _gst_status(company, period),
        "earlier_open_period": (
            {"id": earlier.id, "name": earlier.name} if earlier is not None else None
        ),
        "blockers": blockers,
        "advisory": advisory,
        "can_soft_close": period.status == AccountingPeriod.Status.OPEN and free,
        "can_close": not_closed and free,
        "can_reopen": period.status != AccountingPeriod.Status.OPEN,
    }


def close_summary(company) -> list[dict]:
    """One cheap row per period. Only the first unclosed month gets the full readiness check."""
    from reporting.models import GstReturnPeriod

    periods = list(AccountingPeriod.objects.filter(company=company).order_by("start_date"))
    gst = dict(GstReturnPeriod.objects.filter(company=company).values_list("period", "status"))
    first_unclosed = next((p for p in periods if p.status != AccountingPeriod.Status.CLOSED), None)
    rows = []
    for p in periods:
        row = {
            "id": p.id,
            "name": p.name,
            "start_date": p.start_date.isoformat(),
            "end_date": p.end_date.isoformat(),
            "status": p.status,
            "gst_status": gst.get(period_label(p), GstReturnPeriod.Status.OPEN),
            "blocker_count": None,
            "blocked_by_earlier": False,
        }
        if p.status != AccountingPeriod.Status.CLOSED:
            if first_unclosed is not None and p.id == first_unclosed.id:
                row["blocker_count"] = len(close_readiness(company, p)["blockers"])
            else:
                row["blocked_by_earlier"] = True
        rows.append(row)
    return list(reversed(rows))


# ---------------------------------------------------------------- reopen (ACS-32)
def _fy_close_covering(company, period: AccountingPeriod):
    """A live FY-close journal whose year contains this month, if any."""
    for entry in JournalEntry.objects.filter(
        company=company,
        source_type="FY_CLOSE",
        purpose="FY_CLOSE",
        status=JournalEntry.Status.POSTED,
    ):
        from .reports import fy_bounds_for_end

        start, end = fy_bounds_for_end(company, entry.entry_date)
        if start <= period.end_date and end >= period.start_date:
            return entry
    return None


def assert_can_reopen(company, period: AccountingPeriod) -> str:
    """Return the status the period would move to, or raise with the reason it cannot."""
    from reporting.models import GstReturnPeriod

    if period.status == AccountingPeriod.Status.OPEN:
        raise BusinessRuleError("This period is already open.", code="period_already_open")
    later_closed = AccountingPeriod.objects.filter(
        company=company, start_date__gt=period.end_date, status=AccountingPeriod.Status.CLOSED,
    ).order_by("start_date").first()
    if later_closed is not None:
        raise BusinessRuleError(
            f"{later_closed.name} is closed. Reopen the latest closed month first.",
            code="period_later_closed",
        )
    if _gst_status(company, period) == GstReturnPeriod.Status.CLOSED:
        raise BusinessRuleError(
            "The GST month is closed or filed. Reopen it in GST first.", code="period_gst_closed",
        )
    fy = _fy_close_covering(company, period)
    if fy is not None:
        raise BusinessRuleError(
            "This month is inside a closed financial year. Reverse the year-end close first.",
            code="period_fy_closed",
        )
    return (
        AccountingPeriod.Status.SOFT_CLOSED
        if period.status == AccountingPeriod.Status.CLOSED
        else AccountingPeriod.Status.OPEN
    )


@transaction.atomic
def reopen_period(company, period_id: int, user, reason: str) -> AccountingPeriod:
    reason = (reason or "").strip()
    if not reason:
        raise BusinessRuleError("Give a reason for reopening this period.", code="reason_required")
    period = AccountingPeriod.objects.select_for_update().get(company=company, pk=period_id)
    new_status = assert_can_reopen(company, period)
    before = period.status
    period.status = new_status
    period.updated_by = user
    period.save(update_fields=["status", "updated_by", "updated_at"])
    _after_status_change(company, user, period, before, reason, "period.reopened")
    return period


def _after_status_change(company, user, period, before: str, reason: str, event: str) -> None:
    from django.core.cache import cache

    from core.services.audit import AuditService

    cache.delete(f"bizboard:books-health:{company.id}")
    AuditService.log(
        company=company,
        user=user,
        action="UPDATE",
        entity_type="AccountingPeriod",
        entity_id=period.pk,
        description=event,
        metadata={"before": {"status": before}, "after": {"status": period.status}, "reason": reason, "period": period.name},
    )
    _notify_finance_team(company, user, period, before, reason, event)


def _notify_finance_team(company, user, period, before, reason, event) -> None:
    """Tell the other owners and accountants. Never blocks the reopen if delivery fails."""
    try:
        from accounts.models import CompanyUser
        from core.models import Notification
        from core.services.notifications import NotificationService

        who = getattr(user, "email", "") or "an owner"
        members = CompanyUser.objects.filter(
            company=company, role__in=[CompanyUser.Role.OWNER, CompanyUser.Role.ACCOUNTANT],
        ).select_related("user")
        for member in members:
            if member.user_id == getattr(user, "id", None) or not member.user.email:
                continue
            NotificationService.send(
                company=company,
                channel=Notification.Channel.IN_APP,
                recipient=member.user.email,
                subject=f"{period.name} reopened",
                body=f"{who} moved {period.name} from {before} to {period.status}. Reason: {reason}",
                user=user,
            )
    except Exception:  # noqa: BLE001 — a notification must never undo a reopen
        import logging

        logging.getLogger(__name__).warning("period reopen notification failed", exc_info=True)


# ---------------------------------------------------------------- generate (ACS-33)
def fy_months(company, fy_start_year: int) -> list[tuple[date, date, str]]:
    start_month = int(getattr(company, "fy_start_month", None) or 4)
    out = []
    year, month = fy_start_year, start_month
    for _ in range(12):
        last = monthrange(year, month)[1]
        out.append((date(year, month, 1), date(year, month, last), date(year, month, 1).strftime("%b %Y")))
        month += 1
        if month > 12:
            month, year = 1, year + 1
    return out


@transaction.atomic
def generate_year(company, fy_start_year: int, user) -> dict:
    """Create the 12 monthly periods of a financial year. Existing months are skipped; clashes are refused."""
    if not (2000 <= int(fy_start_year) <= 2100):
        raise BusinessRuleError("Choose a valid financial year.")
    created, skipped = [], []
    months = fy_months(company, int(fy_start_year))
    for start, end, name in months:
        if AccountingPeriod.objects.filter(company=company, start_date=start, end_date=end).exists():
            skipped.append(name)
            continue
        clash = AccountingPeriod.objects.filter(
            company=company, start_date__lte=end, end_date__gte=start,
        ).first()
        if clash is not None:
            raise BusinessRuleError(
                f"{clash.name} ({clash.start_date} to {clash.end_date}) overlaps {name}. "
                "Fix or remove it before generating this year.",
                code="period_overlap",
            )
    for start, end, name in months:
        if name in skipped:
            continue
        AccountingPeriod.objects.create(
            company=company, name=name, start_date=start, end_date=end, created_by=user, updated_by=user,
        )
        created.append(name)
    return {"created": created, "skipped": skipped, "fy_start": months[0][0].isoformat(), "fy_end": months[-1][1].isoformat()}


# ---------------------------------------------------------------- FY close (ACS-34)
def fy_close_preview(company, fy_end: date) -> dict:
    """What closing the year would do, without doing it."""
    from purchases.models import PurchaseInvoice
    from sales.models import SalesInvoice

    from .reports import _fy_close_source_id, fy_bounds_for_end

    fy_start, fy_end = fy_bounds_for_end(company, fy_end)
    rows = (
        JournalLine.objects.filter(
            company=company,
            entry__status__in=[JournalEntry.Status.POSTED, JournalEntry.Status.REVERSED],
            entry__entry_date__gte=fy_start,
            entry__entry_date__lte=fy_end,
            account__type__in=(Account.Type.INCOME, Account.Type.EXPENSE),
        )
        .exclude(entry__purpose="FY_CLOSE")
        .exclude(entry__reversal_of__purpose="FY_CLOSE")
        .values("account__type")
        .annotate(d=Sum("debit"), c=Sum("credit"))
    )
    income = expense = Decimal("0")
    for row in rows:
        d, c = row["d"] or Decimal("0"), row["c"] or Decimal("0")
        if row["account__type"] == Account.Type.INCOME:
            income += c - d
        else:
            expense += d - c
    draft_sales = SalesInvoice.objects.filter(
        company=company, status=SalesInvoice.Status.DRAFT, invoice_date__gte=fy_start, invoice_date__lte=fy_end,
    ).count()
    draft_purchases = PurchaseInvoice.objects.filter(
        company=company, status=PurchaseInvoice.Status.DRAFT, invoice_date__gte=fy_start, invoice_date__lte=fy_end,
    ).count()
    periods = list(
        AccountingPeriod.objects.filter(company=company, start_date__lte=fy_end, end_date__gte=fy_start)
        .order_by("start_date")
        .values("id", "name", "status")
    )
    health = BooksHealthService.control_balances(company)
    unhealthy = (not health["ar"]["healthy"]) or (not health["ap"]["healthy"])
    error_alerts = [a for a in health.get("alerts") or [] if a.get("severity") == "error"]
    already = JournalEntry.objects.filter(
        company=company,
        source_type="FY_CLOSE",
        source_id=_fy_close_source_id(fy_end),
        status=JournalEntry.Status.POSTED,
    ).first()
    blockers = []
    if unhealthy or error_alerts:
        blockers.append("Books health has errors. Fix them in Books Health first.")
    if draft_sales or draft_purchases:
        blockers.append(f"{draft_sales + draft_purchases} draft invoice(s) are dated inside this year.")
    if not periods:
        blockers.append("No accounting periods exist for this year. Create them first.")
    return {
        "fy_start": fy_start.isoformat(),
        "fy_end": fy_end.isoformat(),
        "income": str(income),
        "expense": str(expense),
        "net_profit": str(income - expense),
        "moves_to_account": "3100 Retained Earnings",
        "draft_invoices": draft_sales + draft_purchases,
        "periods": periods,
        "blockers": blockers,
        "can_close": not blockers and already is None,
        "already_closed": already is not None,
        "journal_id": already.id if already is not None else None,
    }


@transaction.atomic
def reverse_fy_close(company, fy_end: date, user, reason: str) -> dict:
    """Undo a year-end close: reverse the closing journal and reopen the year's months.

    The same guards as a single-month reopen apply to the GST months: a filed month stays locked.
    """
    from reporting.models import GstReturnPeriod
    from .reports import _fy_close_source_id, fy_bounds_for_end
    from .services import PostingService

    reason = (reason or "").strip()
    if not reason:
        raise BusinessRuleError("Give a reason for reversing the year-end close.", code="reason_required")
    fy_start, fy_end = fy_bounds_for_end(company, fy_end)
    entry = JournalEntry.objects.select_for_update().filter(
        company=company,
        source_type="FY_CLOSE",
        source_id=_fy_close_source_id(fy_end),
        purpose="FY_CLOSE",
        status=JournalEntry.Status.POSTED,
    ).first()
    if entry is None:
        raise BusinessRuleError("This financial year has not been closed.", code="fy_not_closed")
    later = JournalEntry.objects.filter(
        company=company, source_type="FY_CLOSE", purpose="FY_CLOSE",
        status=JournalEntry.Status.POSTED, entry_date__gt=fy_end,
    ).exists()
    if later:
        raise BusinessRuleError("A later year is also closed. Reverse the latest year first.", code="fy_later_closed")
    filed = GstReturnPeriod.objects.filter(
        company=company,
        period__gte=fy_start.strftime("%Y-%m"),
        period__lte=fy_end.strftime("%Y-%m"),
        status=GstReturnPeriod.Status.CLOSED,
        closed_at__isnull=False,
    )
    # A GST month the FY close itself locked is released with it; a month closed earlier stays a blocker only
    # when its close predates the FY-close journal.
    blocking = [g.period for g in filed if g.closed_at and g.closed_at < entry.posted_at]
    if blocking:
        raise BusinessRuleError(
            f"GST month(s) {', '.join(sorted(blocking))} were closed before the year-end close. "
            "Reopen them in GST first.",
            code="fy_gst_closed",
        )
    # The months go back to soft-closed first: the reversal is dated inside them.
    reopened = AccountingPeriod.objects.filter(
        company=company, start_date__lte=fy_end, end_date__gte=fy_start,
    ).update(status=AccountingPeriod.Status.SOFT_CLOSED, updated_by=user, updated_at=timezone.now())
    GstReturnPeriod.objects.filter(
        company=company,
        period__gte=fy_start.strftime("%Y-%m"),
        period__lte=fy_end.strftime("%Y-%m"),
        status=GstReturnPeriod.Status.CLOSED,
    ).update(status=GstReturnPeriod.Status.SOFT_CLOSED, updated_at=timezone.now())
    PostingService.reverse(entry, user, entry_date=entry.entry_date)
    from django.core.cache import cache

    from core.services.audit import AuditService

    cache.delete(f"bizboard:books-health:{company.id}")
    AuditService.log(
        company=company, user=user, action="UPDATE", entity_type="JournalEntry", entity_id=entry.pk,
        description="fy_close.reversed",
        metadata={"fy_end": fy_end.isoformat(), "reason": reason, "periods_reopened": reopened},
    )
    return {"fy_end": fy_end.isoformat(), "journal_id": entry.id, "periods_reopened": reopened}
