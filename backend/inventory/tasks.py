"""Inventory background tasks."""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def record_expiry_bands_task():
    """B8-005: daily near-expiry sweep — record ExpiryAlertLog bands and send the
    customer notifications that used to fire (per viewer!) from a GET.
    """
    from core.rls import iter_company_ids, set_rls_company

    from .item_stock import expiry_horizon_rows, record_expiry_bands

    swept = 0
    for cid in iter_company_ids():
        set_rls_company(cid)
        from accounts.models import Company

        company = Company.objects.filter(pk=cid).first()
        if company is None:
            continue
        try:
            rows = expiry_horizon_rows(company, days=90)
            record_expiry_bands(company, rows)
            swept += 1
        except Exception:  # noqa: BLE001
            logger.exception("expiry band sweep failed for company %s", cid)
    set_rls_company(None)
    return {"companies": swept}
