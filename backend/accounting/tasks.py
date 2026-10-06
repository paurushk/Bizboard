import datetime
import logging

from celery import shared_task
from django.db import models, transaction
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.rls import set_rls_company

from .models import FixedAsset, JournalEntry
from .services import PostingService

logger = logging.getLogger(__name__)


def _charge_month_bounds(today=None):
    """B1-007: the beat fires 00:05 on the 1st, so a run represents the month
    that just ended. Anchor the charge to the LAST day of that month so a slip
    to the 1st/2nd (or across the FY boundary) doesn't push the entry into the
    next period. Returns (month_key 'YYYY-MM', last_day date, first_day date)."""
    today = today or timezone.localdate()
    last_day_prev = today.replace(day=1) - datetime.timedelta(days=1)
    first_day_prev = last_day_prev.replace(day=1)
    return f"{last_day_prev:%Y-%m}", last_day_prev, first_day_prev


# B1-005: how many prior months a single run may back-fill. A slipped / failed
# cycle costs one month; more than a quarter behind means the scheduler was off
# and a human should reconcile rather than the task posting a year of history at
# today's rate.
_MAX_CATCHUP_MONTHS = 3


def _month_end(d):
    return (d.replace(day=1) + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(days=1)


def _pending_charge_months(charge_date):
    """Charge month-ends from newest back to at most _MAX_CATCHUP_MONTHS ago."""
    months = []
    cur = charge_date
    for _ in range(_MAX_CATCHUP_MONTHS):
        months.append(cur)
        cur = _month_end(cur.replace(day=1) - datetime.timedelta(days=1))
    return months


def _months_before_window(charge_date, earliest_month_end):
    """Month-ends older than the automatic window, down to the acquisition month.

    The scheduler still posts only `_MAX_CATCHUP_MONTHS`. These older months
    are remembered so a long outage does not drop them.
    """
    window = _pending_charge_months(charge_date)
    if not window or earliest_month_end is None:
        return []
    oldest = window[-1]
    months = []
    cur = _month_end(oldest.replace(day=1) - datetime.timedelta(days=1))
    guard = 0
    while cur >= earliest_month_end and guard < 120:
        months.append(cur)
        cur = _month_end(cur.replace(day=1) - datetime.timedelta(days=1))
        guard += 1
    months.reverse()
    return months


def _prorate_days_in_service(locked, cm, amount):
    """Acquisition and disposal months, for SLM and WDV, by days in service."""
    from decimal import ROUND_HALF_UP, Decimal as _D

    days_in_month = (cm - cm.replace(day=1)).days + 1
    start = cm.replace(day=1)
    end = cm
    acquired = locked.acquisition_date
    disposed = getattr(locked, "disposed_at", None)
    if acquired and _month_end(acquired) == cm and acquired > start:
        start = acquired
    if disposed and _month_end(disposed) == cm and disposed < end:
        end = disposed
    if end < start or days_in_month <= 0:
        return _D("0.00")
    days_in_service = (end - start).days + 1
    if 0 < days_in_service < days_in_month:
        amount = (amount * _D(days_in_service) / _D(days_in_month)).quantize(
            _D("0.01"), rounding=ROUND_HALF_UP,
        )
    return amount


def _depreciation_already_posted(locked, cm) -> bool:
    m_start = cm.replace(day=1)
    purpose = f"DEPRECIATION-{cm:%Y-%m}"
    return JournalEntry.objects.filter(
        company=locked.company,
        source_type="FIXED_ASSET",
        source_id=locked.id,
        status=JournalEntry.Status.POSTED,
    ).filter(
        models.Q(purpose=purpose)
        | models.Q(
            purpose__startswith="DEPRECIATION-",
            entry_date__range=(m_start, cm),
        )
    ).exists()


def _depreciate_company_assets(company_id) -> int:
    from decimal import Decimal as _D

    count = 0
    _key, charge_date, _start = _charge_month_bounds()
    # oldest missing month first so the running book value stays correct
    charge_months = list(reversed(_pending_charge_months(charge_date)))
    assets = FixedAsset.objects.filter(
        company_id=company_id, status=FixedAsset.Status.ACTIVE
    ).select_related("company")
    for asset in assets:
        try:
            with transaction.atomic():
                # B1-024: explicit company_id, not just RLS, scopes this lock —
                # a latent cross-tenant hazard if RLS is ever not set for the worker.
                locked = FixedAsset.objects.select_for_update().get(pk=asset.pk, company_id=company_id)
                if locked.status != FixedAsset.Status.ACTIVE:
                    continue
                # B1-005: post EVERY still-missing month (bounded), each dated to
                # its own month-end, so one failed/slipped cycle doesn't lose a
                # month forever.
                skipped_months: list[str] = []
                for cm in charge_months:
                    if cm > charge_date:
                        continue
                    if locked.acquisition_date and cm < _month_end(locked.acquisition_date):
                        continue
                    m_key = f"{cm:%Y-%m}"
                    m_start = cm.replace(day=1)
                    purpose = f"DEPRECIATION-{m_key}"
                    already_posted = JournalEntry.objects.filter(
                        company=locked.company,
                        source_type="FIXED_ASSET",
                        source_id=locked.id,
                        status=JournalEntry.Status.POSTED,
                    ).filter(
                        models.Q(purpose=purpose)
                        | models.Q(
                            purpose__startswith="DEPRECIATION-",
                            entry_date__range=(m_start, cm),
                        )
                    ).exists()
                    if already_posted:
                        continue
                    # ACC-09: never depreciate below salvage; true up a sub-rupee
                    # residual on the last charge.
                    floor = locked.salvage_value or _D("0")
                    remaining = locked.acquisition_cost - locked.depreciated_amount - floor
                    if remaining <= 0:
                        break
                    amount = min(locked.monthly_depreciation, remaining)
                    if amount <= 0:
                        break
                    # Days in service for the acquisition month and the disposal
                    # month, for both SLM and WDV. A full month is unchanged.
                    amount = _prorate_days_in_service(locked, cm, amount)
                    if amount <= 0:
                        continue
                    if remaining - amount <= _D("1"):
                        amount = remaining
                    try:
                        with transaction.atomic():  # savepoint per month
                            entry = PostingService.post(
                                company=locked.company,
                                source_type="FIXED_ASSET",
                                source_id=locked.id,
                                purpose=purpose,
                                entry_date=cm,
                                narration=f"SLM depreciation: {locked.name}",
                                lines=[
                                    {"account": locked.depreciation_expense_account, "debit": amount},
                                    {"account": locked.accumulated_depreciation_account, "credit": amount},
                                ],
                            )
                    except BusinessRuleError as exc:
                        # A closed month is recorded and not added to depreciated_amount.
                        # A later open month must not wipe that message.
                        skipped_months.append(f"{m_key}: {exc}")
                        locked.last_depreciation_error = "; ".join(skipped_months)[:500]
                        locked.save(update_fields=["last_depreciation_error", "updated_at"])
                        logger.warning(
                            "Depreciation month %s skipped for asset %s: %s",
                            m_key, locked.id, exc,
                        )
                        continue
                    if entry:
                        locked.depreciated_amount += amount
                        if not skipped_months:
                            locked.last_depreciation_error = ""
                        else:
                            locked.last_depreciation_error = "; ".join(skipped_months)[:500]
                        locked.save(
                            update_fields=[
                                "depreciated_amount", "last_depreciation_error", "updated_at",
                            ]
                        )
                        count += 1
                earliest = _month_end(locked.acquisition_date) if locked.acquisition_date else None
                older_missing = [
                    f"{cm:%Y-%m}"
                    for cm in _months_before_window(charge_date, earliest)
                    if not _depreciation_already_posted(locked, cm)
                ]
                catchup = ",".join(older_missing)[:800]
                if catchup != (locked.depreciation_catchup_months or ""):
                    locked.depreciation_catchup_months = catchup
                    locked.save(update_fields=["depreciation_catchup_months", "updated_at"])
        except BusinessRuleError as exc:
            logger.warning("Depreciation skipped for asset %s: %s", asset.id, exc)
            FixedAsset.objects.filter(pk=asset.pk).update(last_depreciation_error=str(exc))
        except Exception as exc:
            logger.exception("Depreciation failed for asset %s", asset.id)
            FixedAsset.objects.filter(pk=asset.pk).update(last_depreciation_error=str(exc))
    return count


def backfill_depreciation_catchup(company_id) -> int:
    """Post depreciation months the automatic window refused to drop.

    Explicit only. The nightly task records those months; this posts them,
    oldest first, and clears each one once a journal exists.
    """
    from decimal import Decimal as _D

    set_rls_company(company_id)
    posted_count = 0
    assets = FixedAsset.objects.filter(
        company_id=company_id, status=FixedAsset.Status.ACTIVE,
    ).exclude(depreciation_catchup_months="")
    for asset in assets:
        keys = [part for part in (asset.depreciation_catchup_months or "").split(",") if part]
        if not keys:
            continue
        with transaction.atomic():
            locked = FixedAsset.objects.select_for_update().get(pk=asset.pk, company_id=company_id)
            if locked.status != FixedAsset.Status.ACTIVE:
                continue
            still = []
            for key in keys:
                year, month = int(key[:4]), int(key[5:7])
                cm = _month_end(datetime.date(year, month, 1))
                if _depreciation_already_posted(locked, cm):
                    continue
                floor = locked.salvage_value or _D("0")
                remaining = locked.acquisition_cost - locked.depreciated_amount - floor
                if remaining <= 0:
                    continue
                amount = min(locked.monthly_depreciation, remaining)
                if amount <= 0:
                    still.append(key)
                    continue
                amount = _prorate_days_in_service(locked, cm, amount)
                if amount <= 0:
                    continue
                if remaining - amount <= _D("1"):
                    amount = remaining
                purpose = f"DEPRECIATION-{key}"
                try:
                    with transaction.atomic():
                        entry = PostingService.post(
                            company=locked.company,
                            source_type="FIXED_ASSET",
                            source_id=locked.id,
                            purpose=purpose,
                            entry_date=cm,
                            narration=f"SLM depreciation: {locked.name}",
                            lines=[
                                {"account": locked.depreciation_expense_account, "debit": amount},
                                {"account": locked.accumulated_depreciation_account, "credit": amount},
                            ],
                        )
                except BusinessRuleError as exc:
                    locked.last_depreciation_error = f"{key}: {exc}"[:500]
                    still.append(key)
                    continue
                if entry:
                    locked.depreciated_amount += amount
                    posted_count += 1
                else:
                    still.append(key)
            locked.depreciation_catchup_months = ",".join(still)[:800]
            locked.save(update_fields=[
                "depreciated_amount", "depreciation_catchup_months",
                "last_depreciation_error", "updated_at",
            ])
    return posted_count


@shared_task
def post_monthly_depreciation():
    """Orchestrator: fan out one task per company so Celery RLS GUC is set."""
    from accounts.models import Company

    # B1-024: a company with accounting off has no FixedAsset postings to make
    # — `_depreciate_company_assets` would load every asset, call `.post()`,
    # get None back, and record nothing. Skip queuing the wasted task/queries.
    queued = 0
    for company_id in Company.objects.filter(accounting_enabled=True).values_list(
        "pk", flat=True
    ).iterator():
        post_monthly_depreciation_for_company.delay(company_id=company_id)
        queued += 1
    return queued


@shared_task
def post_monthly_depreciation_for_company(company_id):
    """SLM depreciation for one tenant. Safe to re-run due to source idempotency."""
    set_rls_company(company_id)
    return _depreciate_company_assets(company_id)


def backfill_cache_key(company_id) -> str:
    return f"accounting-backfill:{company_id}"


@shared_task
def run_owner_accounting_backfill(company_id, user_id):
    """Idempotent owner back-fill. Safe to run again; posted journals are skipped."""
    from django.contrib.auth import get_user_model
    from django.core.cache import cache

    from accounting.views import perform_accounting_backfill
    from accounts.models import Company

    key = backfill_cache_key(company_id)
    try:
        set_rls_company(company_id)
        company = Company.objects.get(pk=company_id)
        user = get_user_model().objects.filter(pk=user_id).first()
        payload = perform_accounting_backfill(company, user, dry_run=False)
    except Exception as exc:  # noqa: BLE001 — surface the failure instead of a stuck "running"
        cache.set(key, {"status": "failed", "error": str(exc)[:300]}, 3600)
        raise
    payload["status"] = "done"
    cache.set(key, payload, 3600)
    return payload
