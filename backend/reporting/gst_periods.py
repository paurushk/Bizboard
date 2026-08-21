"""GST return period helpers — soft-close + dirty-after-snapshot."""

from __future__ import annotations

from django.utils import timezone

from core.exceptions import BusinessRuleError

from .models import GstReturnPeriod


def get_or_create_period(company, period: str) -> GstReturnPeriod:
    obj, _ = GstReturnPeriod.objects.get_or_create(company=company, period=period)
    return obj


def mark_period_dirty_if_snapshotted(company, doc_date) -> GstReturnPeriod | None:
    """If a completed/amended doc falls in a period that has been exported, mark dirty."""
    if doc_date is None:
        return None
    period = f"{doc_date.year:04d}-{doc_date.month:02d}"
    from .models import GstReturnSnapshot

    if not GstReturnSnapshot.objects.filter(
        company=company, period=period, return_type=GstReturnSnapshot.ReturnType.GSTR1
    ).exists():
        return None
    obj = get_or_create_period(company, period)
    if not obj.dirty_after_snapshot:
        obj.dirty_after_snapshot = True
        obj.save(update_fields=["dirty_after_snapshot", "updated_at"])
    return obj


def soft_close_period(company, period: str, user) -> GstReturnPeriod:
    obj = get_or_create_period(company, period)
    obj.status = GstReturnPeriod.Status.SOFT_CLOSED
    obj.closed_at = timezone.now()
    obj.closed_by = user
    obj.save(update_fields=["status", "closed_at", "closed_by", "updated_at"])
    return obj


def reopen_period(company, period: str) -> GstReturnPeriod:
    obj = get_or_create_period(company, period)
    obj.status = GstReturnPeriod.Status.OPEN
    obj.closed_at = None
    obj.closed_by = None
    obj.save(update_fields=["status", "closed_at", "closed_by", "updated_at"])
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
    try:
        gst_period = GstReturnPeriod.objects.get(company=company, period=period)
    except GstReturnPeriod.DoesNotExist:
        gst_period = None
    gst_blocking = [GstReturnPeriod.Status.CLOSED]
    if not allow_soft_closed:
        gst_blocking.append(GstReturnPeriod.Status.SOFT_CLOSED)
    if gst_period is not None and gst_period.status in gst_blocking:
        raise BusinessRuleError(
            f"Cannot amend money fields: GST period {period} is {gst_period.status}."
        )

    from accounting.models import AccountingPeriod

    acct_blocking = [AccountingPeriod.Status.CLOSED]
    if not allow_soft_closed:
        acct_blocking.append(AccountingPeriod.Status.SOFT_CLOSED)
    blocking = AccountingPeriod.objects.filter(
        company=company,
        start_date__lte=doc_date,
        end_date__gte=doc_date,
        status__in=acct_blocking,
    ).first()
    if blocking is not None:
        raise BusinessRuleError(
            f"Cannot amend money fields: accounting period covering {doc_date} is {blocking.status}."
        )
