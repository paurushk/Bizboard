"""GST return period helpers — soft-close + dirty-after-snapshot."""

from __future__ import annotations

from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.help_codes import HelpCode

from .models import GstReturnPeriod


def get_or_create_period(company, period: str) -> GstReturnPeriod:
    obj, _ = GstReturnPeriod.objects.get_or_create(company=company, period=period)
    return obj


def mark_period_dirty_if_snapshotted(company, doc_date) -> GstReturnPeriod | None:
    """If a completed/amended doc falls in a period that has been exported, mark dirty.

    PER-01: a document change can invalidate *any* return already snapshotted for
    that month (GSTR-1, 3B, 9, …), not only GSTR-1 — a tenant who exported the 3B
    pack and then amends an invoice must still be told the export is stale.
    """
    if doc_date is None:
        return None
    period = f"{doc_date.year:04d}-{doc_date.month:02d}"
    from .models import GstReturnSnapshot

    if not GstReturnSnapshot.objects.filter(company=company, period=period).exists():
        return None
    obj = get_or_create_period(company, period)
    if not obj.dirty_after_snapshot:
        obj.dirty_after_snapshot = True
        obj.save(update_fields=["dirty_after_snapshot", "updated_at"])
    return obj


def soft_close_period(company, period: str, user) -> GstReturnPeriod:
    # B5-022: period lock no longer auto-ACCEPTs IMS rows (ITC needs an explicit
    # decision) — the old deemed_accept_on_period_lock() call was a dead no-op.
    # CR-104: lock the period row so concurrent Complete cannot race soft-close.
    from django.db import transaction

    with transaction.atomic():
        obj = get_or_create_period(company, period)
        obj = GstReturnPeriod.objects.select_for_update().get(pk=obj.pk, company=company)
        obj.status = GstReturnPeriod.Status.SOFT_CLOSED
        obj.closed_at = timezone.now()
        obj.closed_by = user
        obj.save(update_fields=["status", "closed_at", "closed_by", "updated_at"])
    return obj


def reopen_period(company, period: str) -> GstReturnPeriod:
    from django.db import transaction

    with transaction.atomic():
        obj = get_or_create_period(company, period)
        obj = GstReturnPeriod.objects.select_for_update().get(pk=obj.pk, company=company)
        obj.status = GstReturnPeriod.Status.OPEN
        obj.closed_at = None
        obj.closed_by = None
        obj.save(update_fields=["status", "closed_at", "closed_by", "updated_at"])
    # PER-02: reopening only flips the status flag. Any IMS accept / ITC-reclass
    # journals were posted by an explicit reviewer decision (soft-close itself
    # posts nothing) and intentionally stay. Record the reopen in the audit trail.
    import logging

    from core.models import AuditEvent

    logging.getLogger(__name__).info(
        "GST period %s reopened for company %s.", period, getattr(company, "id", None),
    )
    try:
        AuditEvent.objects.create(
            company=company,
            action="gst_period.reopen",
            entity_type="GstReturnPeriod",
            entity_id=str(obj.pk),
            description=(
                f"Reopened GST period {period}. Any ITC-reclass journals from "
                "explicit IMS decisions are retained (not reversed)."
            ),
        )
    except Exception:  # noqa: BLE001 — audit write must not break the reopen
        pass
    return obj


def period_complete_warning(company, doc_date) -> str | None:
    """Warn-only when completing into a soft-closed / closed period."""
    if doc_date is None:
        return None
    period = f"{doc_date.year:04d}-{doc_date.month:02d}"
    try:
        obj = GstReturnPeriod.objects.get(company=company, period=period)
    except GstReturnPeriod.DoesNotExist:
        return None
    if obj.status in (GstReturnPeriod.Status.SOFT_CLOSED, GstReturnPeriod.Status.CLOSED):
        return f"Document date falls in {obj.status} GST period {period}."
    return None


def assert_period_allows_money_amend(company, doc_date, *, allow_soft_closed=False) -> None:
    """Hard-block money amends / operational posts in locked periods.

    Matches ``PostingService.post``: CLOSED always blocks. SOFT_CLOSED blocks
    new money (Complete, H9 price amend, payroll run, WO release) unless
    ``allow_soft_closed=True`` (cancel / reverse unwind before hard close).
    GST period ``period_complete_warning`` remains warn-only for Complete UX.
    """
    if doc_date is None:
        return
    if isinstance(doc_date, str):
        from datetime import date as date_cls

        doc_date = date_cls.fromisoformat(str(doc_date)[:10])
    period = f"{doc_date.year:04d}-{doc_date.month:02d}"
    # CR-104: lock GST period row when present so soft_close cannot flip under us.
    from django.db import transaction

    with transaction.atomic():
        # CR-156 / CR-104 residual: always materialize + lock the GST period row so
        # concurrent soft_close cannot create+SOFT_CLOSE after a no-row assert.
        gst_period = get_or_create_period(company, period)
        gst_period = GstReturnPeriod.objects.select_for_update().get(pk=gst_period.pk, company=company)
        gst_blocking = [GstReturnPeriod.Status.CLOSED]
        if not allow_soft_closed:
            gst_blocking.append(GstReturnPeriod.Status.SOFT_CLOSED)
        if gst_period.status in gst_blocking:
            raise BusinessRuleError(
                f"Cannot amend money fields: GST period {period} is {gst_period.status}.",
                code=HelpCode.CLOSED_PERIOD,
            )

        from accounting.models import AccountingPeriod

        acct_blocking = [AccountingPeriod.Status.CLOSED]
        if not allow_soft_closed:
            acct_blocking.append(AccountingPeriod.Status.SOFT_CLOSED)
        blocking = (
            AccountingPeriod.objects.select_for_update()
            .filter(
                company=company,
                start_date__lte=doc_date,
                end_date__gte=doc_date,
                status__in=acct_blocking,
            )
            .first()
        )
        if blocking is not None:
            raise BusinessRuleError(
                f"Cannot amend money fields: accounting period covering {doc_date} is {blocking.status}.",
                code=HelpCode.CLOSED_PERIOD,
            )

        # ACC-04 (B1-006): opt-in — the date must fall inside an OPEN period, not
        # merely avoid a closed one. Mirrors PostingService.post so the manual
        # journal-post action and every other caller enforce it consistently.
        if getattr(company, "require_open_period_for_posting", False):
            in_open = AccountingPeriod.objects.filter(
                company=company,
                start_date__lte=doc_date,
                end_date__gte=doc_date,
                status=AccountingPeriod.Status.OPEN,
            ).exists()
            if not in_open:
                raise BusinessRuleError(
                    f"{doc_date} is not inside an open accounting period. "
                    "Create the period (or open it) before posting.",
                    code=HelpCode.CLOSED_PERIOD,
                )


def _months_in_range(start, end) -> list[str]:
    from datetime import date as date_cls

    months: list[str] = []
    year, month = start.year, start.month
    while date_cls(year, month, 1) <= end:
        months.append(f"{year:04d}-{month:02d}")
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
        if len(months) > 24:
            break
    return months


def gst_period_open_warnings(company, period_start, period_end=None) -> list[dict]:
    """R-050: warn when an accounting close leaves the GST month OPEN. No dual-write."""
    end = period_end or period_start
    for period in _months_in_range(period_start, end):
        obj = GstReturnPeriod.objects.filter(company=company, period=period).first()
        if obj is None or obj.status == GstReturnPeriod.Status.OPEN:
            return [{"code": "gst_period_open"}]
    return []


def accounting_period_open_warnings(company, period: str) -> list[dict]:
    """Inverse of gst_period_open_warnings — GST soft-close while books stay OPEN."""
    from calendar import monthrange
    from datetime import date as date_cls

    from accounting.models import AccountingPeriod

    try:
        year, month = int(str(period)[:4]), int(str(period)[5:7])
        start = date_cls(year, month, 1)
        end = date_cls(year, month, monthrange(year, month)[1])
    except (TypeError, ValueError):
        return []
    if AccountingPeriod.objects.filter(
        company=company,
        start_date__lte=end,
        end_date__gte=start,
        status=AccountingPeriod.Status.OPEN,
    ).exists():
        return [{"code": "accounting_period_open"}]
    return []
