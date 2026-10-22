"""Inventory background tasks."""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def release_expired_reservations_task():
    """Release stock holds that have passed their expiry. Runs every 15 minutes."""
    from django.utils import timezone

    from core.rls import company_ids_having, set_rls_company

    from accounts.models import Company

    from .models import StockReservation
    from .services import InventoryService

    released_companies = 0
    # WP-E1: visit only companies with an expired hold, not every tenant every 15 minutes.
    expired = company_ids_having(StockReservation, released_at__isnull=True, expires_at__lte=timezone.now())
    for cid in expired:  # inline-company-loop-ok: only companies with an expired hold
        set_rls_company(cid)
        company = Company.objects.filter(pk=cid).first()
        if company is None:
            continue
        try:
            InventoryService.release_expired_reservations(company)
            released_companies += 1
        except Exception:  # noqa: BLE001
            logger.exception("expired reservation release failed for company %s", cid)
    set_rls_company(None)
    return {"companies": released_companies}


@shared_task
def record_expiry_bands_task():
    """B8-005: daily near-expiry sweep — record ExpiryAlertLog bands and send the
    customer notifications that used to fire (per viewer!) from a GET.
    """
    from core.rls import company_ids_having

    from .models import BatchLot

    # WP-E1: one task per company with dated batches (the worker sets RLS from company_id).
    ids = company_ids_having(BatchLot, expiry_date__isnull=False)
    for cid in ids:
        record_expiry_bands_company_task.delay(company_id=cid)
    return {"queued": len(ids)}


@shared_task
def record_expiry_bands_company_task(company_id=None):
    from accounts.models import Company

    from .item_stock import expiry_horizon_rows, record_expiry_bands

    company = Company.objects.filter(pk=company_id).first()
    if company is None:
        return {"company_id": company_id, "ok": False}
    rows = expiry_horizon_rows(company, days=90)
    record_expiry_bands(company, rows)
    return {"company_id": company_id, "ok": True}


@shared_task
def verify_stock_balances_integrity():
    """CR-042: Scheduled task checking StockBalance.on_hand == Sum(StockMovement.quantity).
    Automatically repairs any drifted balance rows using rebuild_balance.
    """
    from decimal import Decimal
    from django.db.models import Sum

    from accounts.models import Company
    from core.rls import iter_company_ids, set_rls_company

    from .models import StockBalance, StockMovement
    from .services import InventoryService

    repaired_total = 0
    for cid in iter_company_ids():  # inline-company-loop-ok: manual repair path, not on beat
        set_rls_company(cid)
        company = Company.objects.filter(pk=cid).first()
        if company is None:
            continue
        try:
            movement_sums = {
                (m["warehouse_id"], m["product_id"], m["batch_id"]): Decimal(str(m["total"] or 0))
                for m in StockMovement.objects.filter(company=company)
                .values("warehouse_id", "product_id", "batch_id")
                .annotate(total=Sum("quantity"))
            }
            balances = StockBalance.objects.filter(company=company).select_related("product", "warehouse")
            for b in balances:
                expected = movement_sums.get((b.warehouse_id, b.product_id, b.batch_id), Decimal("0"))
                if b.on_hand != expected:
                    logger.warning(
                        "Stock balance drift detected for company %s, product %s, warehouse %s, batch %s: cached %s vs movement %s. Repairing.",
                        cid, b.product_id, b.warehouse_id, b.batch_id, b.on_hand, expected,
                    )
                    InventoryService.rebuild_balance(company, b.product, warehouse=b.warehouse, batch=b.batch)
                    if b.product.track_batch:
                        InventoryService.reconcile_batch_reservations(company, b.product, warehouse=b.warehouse)
                    repaired_total += 1
        except Exception:
            logger.exception("Stock balance integrity check failed for company %s", cid)
    set_rls_company(None)
    return {"repaired_balances": repaired_total}
