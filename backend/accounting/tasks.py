from celery import shared_task
from django.db import transaction
from django.utils import timezone
import logging

from core.exceptions import BusinessRuleError

from .models import FixedAsset
from .services import PostingService

logger = logging.getLogger(__name__)


@shared_task
def post_monthly_depreciation():
    """SLM depreciation; safe to re-run due to source idempotency. Isolates per-asset failures."""
    count = 0
    for asset in FixedAsset.objects.filter(status=FixedAsset.Status.ACTIVE).select_related("company"):
        try:
            with transaction.atomic():
                locked = FixedAsset.objects.select_for_update().get(pk=asset.pk)
                if locked.status != FixedAsset.Status.ACTIVE:
                    continue
                remaining = locked.acquisition_cost - locked.depreciated_amount
                amount = min(locked.monthly_depreciation, remaining)
                if amount <= 0:
                    continue
                entry = PostingService.post(
                    company=locked.company,
                    source_type="FIXED_ASSET",
                    source_id=locked.id,
                    purpose=f"DEPRECIATION-{timezone.localdate():%Y-%m}",
                    entry_date=timezone.localdate(),
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
