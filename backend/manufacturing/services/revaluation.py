"""QOS-0146: re-price finished stock on hand to the standard cost in force.

Preview first (nothing moves), then post. A posted run takes each lot out at its current cost and puts it
back at the standard through the stock ledger, so the running cost, the FIFO layers and the stock report
all agree afterwards, and the difference is one journal: Inventory against Manufacturing Variance.
A run is reversed as a whole, and only while none of its lots has moved since.
"""

from accounting.books import posts_to_ledger
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core.services.audit import AuditService
from inventory.models import (
    InventoryCostLayer, InventoryRunningCost, MovementType, StockBalance, StockMovement, Warehouse,
)
from inventory.services import InventoryService
from manufacturing.models import (
    DocumentStatus, StandardCost, StandardRevaluation, StandardRevaluationLine,
)

from .common import ZERO, assert_doc_date, d, money, next_number, rule, unit4

JOURNAL = "MFG_REVALUE"


def _in_force(company, product_id, as_of):
    return (
        StandardCost.objects.filter(company=company, product_id=product_id, effective_from__lte=as_of)
        .order_by("-effective_from").first()
    )


def _current_unit_cost(company, balance) -> Decimal:
    """What one unit of this lot is carried at right now (the same number the next issue would use)."""
    method = getattr(company, "inventory_valuation_method", "WAVG") or "WAVG"
    key = dict(company=company, warehouse_id=balance.warehouse_id, product_id=balance.product_id,
               batch_id=balance.batch_id)
    if method == "FIFO":
        layers = InventoryCostLayer.objects.filter(**key, qty_remaining__gt=0)
        qty = sum((d(x.qty_remaining) for x in layers), ZERO)
        value = sum((d(x.qty_remaining) * d(x.unit_cost) for x in layers), ZERO)
        return unit4(value / qty) if qty else ZERO
    row = InventoryRunningCost.objects.filter(**key).first()
    return unit4(d(row.value) / d(row.qty)) if row is not None and d(row.qty) else ZERO


# Scrap is valued at what it recovers and stock at a job worker is somebody else's to process: neither is re-priced.
REPRICED_KINDS = (Warehouse.Kind.NORMAL, Warehouse.Kind.QUARANTINE)


def _plan(company, as_of, product=None, *, lock=False):
    """The lots that would change: (balance, old_unit, new_unit) for every lot not already at the standard.

    ``lock`` takes the stock balances for the rest of the transaction, so nothing can be issued from a lot between
    reading it and moving it.
    """
    from masters.models import Product

    if product is not None:
        products = [product]
    else:
        ids = (
            StandardCost.objects.filter(company=company, effective_from__lte=as_of)
            .values_list("product_id", flat=True).distinct()
        )
        products = list(Product.objects.filter(company=company, pk__in=ids))
    plan = []
    for prod in products:
        std = _in_force(company, prod.pk, as_of)
        if std is None or std.unit_cost <= 0:
            if product is not None:
                raise rule(f"'{prod.name}' has no standard cost in force on that date.", "MFG_REVAL_NO_STANDARD")
            continue
        if prod.track_serial:
            if product is not None:
                raise rule(
                    f"'{prod.name}' is tracked by serial number; its stock cannot be re-priced in bulk.",
                    "MFG_REVAL_SERIAL",
                )
            continue
        new_unit = unit4(std.unit_cost)
        balances = StockBalance.objects.filter(
            company=company, product=prod, on_hand__gt=0, warehouse__kind__in=REPRICED_KINDS,
        ).order_by("id")
        if lock:
            # of=("self",): the join to a nullable batch cannot be locked on PostgreSQL.
            balances = balances.select_for_update(of=("self",))
        for bal in balances:
            old_unit = _current_unit_cost(company, bal)
            if old_unit == new_unit:
                continue
            plan.append((bal, old_unit, new_unit))
    return plan


def _fill(run, plan):
    run.lines.all().delete()
    before = after = ZERO
    for bal, old_unit, new_unit in plan:
        qty = d(bal.on_hand)
        old_value, new_value = money(qty * old_unit), money(qty * new_unit)
        StandardRevaluationLine.objects.create(
            run=run, company=run.company, product_id=bal.product_id, warehouse_id=bal.warehouse_id,
            batch_id=bal.batch_id, qty=qty, old_unit_cost=old_unit, new_unit_cost=new_unit,
            old_value=old_value, new_value=new_value,
        )
        before += old_value
        after += new_value
    run.total_before, run.total_after = before, after
    run.save(update_fields=["total_before", "total_after", "updated_at"])


@transaction.atomic
def preview(company, user, *, as_of=None, product=None, notes="") -> StandardRevaluation:
    as_of = as_of or timezone.localdate()
    if as_of > timezone.localdate():
        raise rule("Choose today or an earlier date.", "MFG_REVAL_FUTURE")
    run = StandardRevaluation.objects.create(
        company=company, as_of=as_of, product=product, notes=(notes or "")[:500],
        created_by=user, updated_by=user,
    )
    _fill(run, _plan(company, as_of, product))
    return run


def _lock(run) -> StandardRevaluation:
    return StandardRevaluation.objects.select_for_update().get(pk=run.pk)


@transaction.atomic
def post(run, user, *, can_backdate=True) -> StandardRevaluation:
    run = _lock(run)
    if run.status != DocumentStatus.DRAFT:
        raise rule("This revaluation has already been posted.", "MFG_DOC_NOT_DRAFT")
    company = run.company
    today = timezone.localdate()
    assert_doc_date(company, today, can_backdate=can_backdate, label="Revaluation")
    # Stock may have moved since the preview; what is posted is what is on hand now.
    _fill(run, _plan(company, run.as_of, run.product, lock=True))
    if not run.lines.exists():
        raise rule("Nothing needs re-pricing: stock on hand is already at the standard cost.", "MFG_REVAL_NOTHING")
    before = after = ZERO
    for line in run.lines.select_related("product", "warehouse", "batch"):
        qty = d(line.qty)
        out = InventoryService.post_movement(
            company=company, product=line.product, warehouse=line.warehouse, batch=line.batch,
            movement_type=MovementType.ADJUSTMENT, quantity=-qty, skip_negative_check=True,
            reference_type="mfg_revalue", reference_id=str(run.pk), movement_date=today, user=user,
            reason=f"Re-priced to standard ({run.as_of})", allow_held=True,
        )
        back = InventoryService.post_movement(
            company=company, product=line.product, warehouse=line.warehouse, batch=line.batch,
            movement_type=MovementType.ADJUSTMENT, quantity=qty, unit_cost=line.new_unit_cost,
            reference_type="mfg_revalue", reference_id=str(run.pk), movement_date=today, user=user,
            reason=f"Re-priced to standard ({run.as_of})", allow_held=True,
        )
        # Record what the stock actually gave up, not what the preview estimated.
        line.old_unit_cost = unit4(out.unit_cost or 0)
        line.old_value = money(qty * line.old_unit_cost)
        line.new_value = money(qty * d(line.new_unit_cost))
        line.movement_ids = [out.pk, back.pk]
        line.last_movement_id = back.pk
        line.save(update_fields=["old_unit_cost", "old_value", "new_value", "movement_ids", "last_movement_id"])
        before += line.old_value
        after += line.new_value
    run.total_before, run.total_after = before, after
    run.number = next_number(company, "mfg_revalue", "SR")
    run.status = DocumentStatus.POSTED
    run.posted_at = timezone.now()
    run.updated_by = user
    run.save()
    if posts_to_ledger(company) and run.total_change != 0:
        from accounting.services import PostingService

        PostingService.post_mfg_revaluation(
            company=company, source_type=JOURNAL, source_id=run.pk, purpose="POST", entry_date=today,
            amount=run.total_change, narration=f"{run.number}: stock re-priced to standard cost", user=user,
        )
    AuditService.log(
        action="mfg.revaluation.posted", company=company, user=user, entity_type="StandardRevaluation",
        entity_id=str(run.pk), description=f"{run.number}: {run.lines.count()} lots, change {run.total_change}",
    )
    return run


@transaction.atomic
def reverse(run, user, reason, *, can_backdate=True) -> StandardRevaluation:
    run = _lock(run)
    if run.status != DocumentStatus.POSTED:
        raise rule("Only a posted revaluation can be reversed.", "MFG_DOC_NOT_POSTED")
    if not (reason or "").strip():
        raise rule("Say why the revaluation is being reversed.", "MFG_REASON_REQUIRED")
    company = run.company
    today = timezone.localdate()
    assert_doc_date(company, today, can_backdate=can_backdate, label="Reversal")
    lines = list(run.lines.select_related("product", "warehouse", "batch"))
    for line in lines:
        moved = StockMovement.objects.filter(
            company=company, product_id=line.product_id, warehouse_id=line.warehouse_id, batch_id=line.batch_id,
            pk__gt=line.last_movement_id or 0,
        ).exists()
        if moved:
            raise rule(
                f"'{line.product.name}' has moved since it was re-priced, so the run cannot be reversed as a "
                f"whole. Post a new revaluation at the standard you want instead.",
                "MFG_REVAL_MOVED",
            )
    for line in lines:
        qty = d(line.qty)
        out = InventoryService.post_movement(
            company=company, product=line.product, warehouse=line.warehouse, batch=line.batch,
            movement_type=MovementType.ADJUSTMENT, quantity=-qty, skip_negative_check=True,
            reference_type="mfg_revalue_reverse", reference_id=str(run.pk), movement_date=today, user=user,
            reason=f"Re-pricing {run.number} reversed", allow_held=True,
        )
        back = InventoryService.post_movement(
            company=company, product=line.product, warehouse=line.warehouse, batch=line.batch,
            movement_type=MovementType.ADJUSTMENT, quantity=qty, unit_cost=line.old_unit_cost,
            reference_type="mfg_revalue_reverse", reference_id=str(run.pk), movement_date=today, user=user,
            reason=f"Re-pricing {run.number} reversed", allow_held=True,
        )
        line.movement_ids = list(line.movement_ids or []) + [out.pk, back.pk]
        line.save(update_fields=["movement_ids"])
    if posts_to_ledger(company):
        from accounting.services import PostingService

        PostingService.reverse_mfg_document(
            company=company, source_type=JOURNAL, source_id=run.pk, user=user, entry_date=today,
        )
    run.status = DocumentStatus.REVERSED
    run.reversed_at = timezone.now()
    run.reverse_reason = reason.strip()[:500]
    run.updated_by = user
    run.save()
    AuditService.log(
        action="mfg.revaluation.reversed", company=company, user=user, entity_type="StandardRevaluation",
        entity_id=str(run.pk), description=f"{run.number} reversed: {run.reverse_reason[:200]}",
    )
    return run
