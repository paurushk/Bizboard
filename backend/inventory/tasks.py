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
    for cid in iter_company_ids():
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
