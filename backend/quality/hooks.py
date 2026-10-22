"""Small calls other apps make into quality. Every one is a no-op unless MFG_QUALITY is on."""

from core.exceptions import BusinessRuleError
from core.services.feature_flags import flag_enabled

from .models import Inspection
from .services import create_inspection, find_template, set_batch_status


def enabled(company) -> bool:
    return flag_enabled(company, "MFG_QUALITY")


def assert_grn_inspected(grn, items) -> None:
    """A goods receipt for an item that needs inspection cannot be completed until it has been decided."""
    if not enabled(grn.company):
        return
    for item in items:
        product = item.product
        if not getattr(product, "requires_incoming_inspection", False):
            continue
        latest = (
            Inspection.objects.filter(grn_item=item).exclude(status=Inspection.Status.CANCELLED).order_by("-id").first()
        )
        if latest is None or latest.status != Inspection.Status.COMPLETED or latest.decision not in ("PASS", "FAIL"):
            raise BusinessRuleError(
                f"'{product.name}' must be inspected before this goods receipt is completed.",
                code="QC_INSPECTION_REQUIRED",
            )


def quarantine_target(company, product):
    """The quarantine godown when this item is to be received into quarantine, else None."""
    if not getattr(product, "receive_into_quarantine", False) or not enabled(company):
        return None
    from inventory.aux_warehouses import ensure_aux_warehouse
    from manufacturing.services.common import get_settings

    return get_settings(company).quarantine_warehouse or ensure_aux_warehouse(company, "QUARANTINE")


def mark_quarantined(batch, user=None) -> None:
    if batch is not None:
        set_batch_status(batch, "QUARANTINE", user, "Received into quarantine")


def after_grn_item_received(grn, item, batch, qty, user) -> None:
    """Queue the lab check for a lot that went into quarantine."""
    if batch is None or batch.quality_status != "QUARANTINE":
        return
    create_inspection(
        grn.company, user, product=item.product, qty=qty, source_type=Inspection.Source.BATCH,
        stage="INCOMING", batch=batch, grn_item=item, supplier=grn.supplier,
        notes=f"From goods receipt {grn.number}",
    )


def hold_for_final_inspection(company, product, batch, receipt_id, qty, user):
    """Hold a finished lot for its final check when the item has a final-inspection template."""
    if batch is None or not enabled(company):
        return None
    if find_template(company, product, "FINAL") is None:
        return None
    if Inspection.objects.filter(company=company, receipt_id=receipt_id, batch=batch).exclude(status="CANCELLED").exists():
        return None
    set_batch_status(batch, "HOLD", user, "Awaiting final inspection")
    return create_inspection(
        company, user, product=product, qty=qty, source_type=Inspection.Source.RECEIPT, stage="FINAL",
        batch=batch, receipt_id=receipt_id, notes="Final inspection of a production receipt",
    )


def cancel_for_receipt(company, receipt_id, user) -> None:
    for insp in Inspection.objects.filter(company=company, receipt_id=receipt_id, status=Inspection.Status.DRAFT):
        from .services import cancel_inspection

        cancel_inspection(insp, user)
