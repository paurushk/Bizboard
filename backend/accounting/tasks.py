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
                        # e.g. a back-catch-up month lands in a closed period —
                        # skip it, keep going for the newer months.
                        logger.warning(
                            "Depreciation month %s skipped for asset %s: %s",
                            m_key, locked.id, exc,
                        )
                        continue
                    if entry:
                        locked.depreciated_amount += amount
                        locked.last_depreciation_error = ""
                        locked.save(
                            update_fields=[
                                "depreciated_amount", "last_depreciation_error", "updated_at",
                            ]
                        )
                        count += 1
        except BusinessRuleError as exc:
            logger.warning("Depreciation skipped for asset %s: %s", asset.id, exc)
            FixedAsset.objects.filter(pk=asset.pk).update(last_depreciation_error=str(exc))
        except Exception as exc:
            logger.exception("Depreciation failed for asset %s", asset.id)
            FixedAsset.objects.filter(pk=asset.pk).update(last_depreciation_error=str(exc))
    return count


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
