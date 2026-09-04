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


def _depreciate_company_assets(company_id) -> int:
    count = 0
    month_key, charge_date, month_start = _charge_month_bounds()
    assets = FixedAsset.objects.filter(
        company_id=company_id, status=FixedAsset.Status.ACTIVE
    ).select_related("company")
    for asset in assets:
        try:
            with transaction.atomic():
                locked = FixedAsset.objects.select_for_update().get(pk=asset.pk)
                if locked.status != FixedAsset.Status.ACTIVE:
                    continue
                # ACC-09: never depreciate below salvage; true up a sub-rupee
                # residual on the last charge so the book value lands exactly on
                # salvage instead of leaving a ₹0.01-scale tail forever.
                from decimal import Decimal as _D

                floor = locked.salvage_value or _D("0")
                remaining = locked.acquisition_cost - locked.depreciated_amount - floor
                if remaining <= 0:
                    continue
                amount = min(locked.monthly_depreciation, remaining)
                if amount <= 0:
                    continue
                if remaining - amount <= _D("1"):
                    amount = remaining
                purpose = f"DEPRECIATION-{month_key}"
                already_posted = JournalEntry.objects.filter(
                    company=locked.company,
                    source_type="FIXED_ASSET",
                    source_id=locked.id,
                    status=JournalEntry.Status.POSTED,
                ).filter(
                    # match either the new month-keyed purpose or any legacy
                    # depreciation entry that already lands in this charge month
                    models.Q(purpose=purpose)
                    | models.Q(
                        purpose__startswith="DEPRECIATION-",
                        entry_date__range=(month_start, charge_date),
                    )
                ).exists()
                if already_posted:
                    continue
                entry = PostingService.post(
                    company=locked.company,
                    source_type="FIXED_ASSET",
                    source_id=locked.id,
                    purpose=purpose,
                    entry_date=charge_date,
                    narration=f"SLM depreciation: {locked.name}",
                    lines=[
                        {"account": locked.depreciation_expense_account, "debit": amount},
                        {"account": locked.accumulated_depreciation_account, "credit": amount},
                    ],
                )
                if entry:
                    locked.depreciated_amount += amount
                    locked.last_depreciation_error = ""
                    locked.save(update_fields=["depreciated_amount", "last_depreciation_error", "updated_at"])
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

    queued = 0
    for company_id in Company.objects.values_list("pk", flat=True).iterator():
        post_monthly_depreciation_for_company.delay(company_id=company_id)
        queued += 1
    return queued


@shared_task
def post_monthly_depreciation_for_company(company_id):
    """SLM depreciation for one tenant. Safe to re-run due to source idempotency."""
    set_rls_company(company_id)
    return _depreciate_company_assets(company_id)
