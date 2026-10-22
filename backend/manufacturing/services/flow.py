"""Work order lifecycle for the document flow: release, complete, cancel, close, reopen (MFG-02, MFG-09)."""

from accounting.books import posts_to_ledger
from decimal import Decimal

from django.db import transaction

from core.services.audit import AuditService
from inventory.services import InventoryService, InventoryValuationService

from manufacturing.models import (
    DocumentStatus, MaterialIssue, MaterialIssueLine, MaterialReturn, MaterialReturnLine,
    ProductionReceipt, WorkOrder, WorkOrderVariance,
)

from . import reservation, subcontract
from .bom import assert_no_bom_cycle
from .common import (
    ZERO, assert_doc_date, d, money, resolve_issue_warehouse, rule, unit4,
)
from .issue import assert_documents_allowed, lock_work_order
from .receipt import _additional_cost, produced_so_far


def freeze_estimate(wo) -> Decimal:
    """What the order is expected to cost, split over its outputs (§4.14). Returns the total."""
    material = ZERO
    for line in wo.component_lines.select_related("component"):
        if line.principal_supplied:
            continue
        warehouse = resolve_issue_warehouse(wo, line.component, line=line)
        material += d(line.qty) * d(
            InventoryValuationService.unit_cost(wo.company, line.component, warehouse)
        )
    total = money(material + _additional_cost(wo, d(wo.qty)))
    outputs = list(wo.planned_outputs.all())
    recovery = sum(
        (d(o.qty) * d(o.recovery_rate or 0) for o in outputs if o.kind in ("BY_PRODUCT", "SCRAP")), ZERO,
    )
    pool = max(ZERO, total - recovery)
    co_share = sum((d(o.cost_share_pct) for o in outputs if o.kind == "CO_PRODUCT"), ZERO)
    main_share = Decimal("100") - co_share
    wo.estimated_unit_cost = unit4(pool * main_share / Decimal("100") / d(wo.qty)) if d(wo.qty) else ZERO
    for out in outputs:
        if out.kind == "CO_PRODUCT" and d(out.qty):
            out.estimated_unit_cost = unit4(pool * d(out.cost_share_pct) / Decimal("100") / d(out.qty))
            out.save(update_fields=["estimated_unit_cost"])
    return total


@transaction.atomic
def release_separate(wo, user, *, can_backdate=True) -> WorkOrder:
    from . import _snapshot_bom

    wo = lock_work_order(wo)
    if wo.status != WorkOrder.Status.DRAFT:
        raise rule("Only draft work orders can be released.", "MFG_BAD_WO_STATUS")
    doc_date = assert_doc_date(wo.company, wo.released_at, can_backdate=can_backdate, label="Release")
    if wo.kind == WorkOrder.Kind.STANDARD:
        if wo.bom.status != wo.bom.Status.ACTIVE:
            raise rule("BOM must be ACTIVE to release a work order.", "MFG_BOM_NOT_ACTIVE")
        assert_no_bom_cycle(
            wo.company, wo.bom.product_id, list(wo.bom.lines.values_list("component_id", flat=True)),
            ignore_bom_id=wo.bom_id,
        )
        _snapshot_bom(wo)
    if not wo.component_lines.exists():
        raise rule("The work order has no materials.", "MFG_NO_LINES")
    wo.warehouse = wo.warehouse or InventoryService.default_warehouse(wo.company)
    freeze_estimate(wo)
    reservation.reserve_work_order(wo, user)
    wo.status = WorkOrder.Status.RELEASED
    wo.released_at = doc_date
    wo.updated_by = user
    wo.save()
    AuditService.log(
        action="mfg.wo.released", company=wo.company, user=user, entity_type="WorkOrder",
        entity_id=str(wo.pk), description=f"{wo.number} released",
    )
    return wo


@transaction.atomic
def complete_separate(wo, user, *, can_backdate=True) -> WorkOrder:
    """Mark the order finished (also the way to short-close one that will not reach its plan)."""
    wo = lock_work_order(wo)
    assert_documents_allowed(wo)
    subcontract.assert_nothing_out_with_job_worker(wo)
    if produced_so_far(wo) <= 0:
        raise rule("Post a production receipt before completing the work order.", "MFG_NOTHING_RECEIVED")
    doc_date = assert_doc_date(wo.company, wo.completed_at, can_backdate=can_backdate, label="Completion")
    reservation.release_all(wo)
    wo.status = WorkOrder.Status.COMPLETED
    wo.completed_at = doc_date
    wo.updated_by = user
    wo.save(update_fields=["status", "completed_at", "updated_at", "updated_by"])
    AuditService.log(
        action="mfg.wo.completed", company=wo.company, user=user, entity_type="WorkOrder",
        entity_id=str(wo.pk), description=f"{wo.number} completed",
    )
    return wo


def _posted_docs(wo) -> bool:
    return (
        MaterialIssue.objects.filter(work_order=wo, status=DocumentStatus.POSTED).exists()
        or MaterialReturn.objects.filter(work_order=wo, status=DocumentStatus.POSTED).exists()
        or ProductionReceipt.objects.filter(work_order=wo, status=DocumentStatus.POSTED).exists()
    )


@transaction.atomic
def cancel_separate(wo, user) -> WorkOrder:
    wo = lock_work_order(wo)
    if wo.status in (WorkOrder.Status.CANCELLED, WorkOrder.Status.CLOSED):
        raise rule("This work order can no longer be cancelled.", "MFG_BAD_WO_STATUS")
    if _posted_docs(wo):
        raise rule(
            "Documents have been posted on this work order. Reverse them first, then cancel.",
            "MFG_CANCEL_REVERSE_FIRST",
        )
    subcontract.assert_nothing_out_with_job_worker(wo)
    reservation.release_all(wo)
    wo.status = WorkOrder.Status.CANCELLED
    wo.updated_by = user
    wo.save(update_fields=["status", "updated_at", "updated_by"])
    AuditService.log(
        action="mfg.wo.cancelled", company=wo.company, user=user, entity_type="WorkOrder",
        entity_id=str(wo.pk), description=f"{wo.number} cancelled",
    )
    return wo


# --- close -----------------------------------------------------------------------------------

def _line_actuals(wo):
    """{wo_line_id: [qty, cost]} from posted issue and return documents (substitutes count against their line)."""
    out: dict[int, list] = {}
    for ln in MaterialIssueLine.objects.filter(issue__work_order=wo, issue__status=DocumentStatus.POSTED):
        row = out.setdefault(ln.wo_line_id, [ZERO, ZERO])
        row[0] += d(ln.qty)
        row[1] += d(ln.cost_amount)
    for ln in MaterialReturnLine.objects.filter(
        material_return__work_order=wo, material_return__status=DocumentStatus.POSTED,
    ):
        row = out.setdefault(ln.wo_line_id, [ZERO, ZERO])
        row[0] -= d(ln.qty)
        row[1] -= d(ln.cost_amount)
    return out


@transaction.atomic
def close_work_order(wo, user, *, can_backdate=True) -> WorkOrder:
    """Settle a completed order: record how its materials compare with its output and clear what is left in WIP."""
    wo = lock_work_order(wo)
    if wo.status != WorkOrder.Status.COMPLETED:
        raise rule("Only a completed work order can be closed.", "MFG_BAD_WO_STATUS")
    doc_date = assert_doc_date(wo.company, wo.closed_at, can_backdate=can_backdate, label="Close")
    reservation.release_all(wo)
    made = produced_so_far(wo)
    actuals = _line_actuals(wo)
    wo.variances.all().delete()
    for line in wo.component_lines.select_related("component").filter(alternate_of__isnull=True):
        actual_qty, actual_cost = actuals.get(line.pk, [ZERO, ZERO])
        if actual_qty == 0 and actual_cost == 0:
            continue
        standard_qty = d(line.qty) * made / d(wo.qty) if d(wo.qty) else ZERO
        unit = (actual_cost / actual_qty) if actual_qty else ZERO
        standard_cost = standard_qty * unit
        WorkOrderVariance.objects.create(
            work_order=wo, company=wo.company, kind="USAGE", component=line.component,
            standard_qty=standard_qty.quantize(Decimal("0.001")), actual_qty=actual_qty,
            standard_cost=money(standard_cost), actual_cost=money(actual_cost),
            variance=money(actual_cost - standard_cost),
        )
    # A different material standing in for a listed one is worth seeing on its own.
    for ln in MaterialIssueLine.objects.filter(
        issue__work_order=wo, issue__status=DocumentStatus.POSTED, wo_line__isnull=False,
    ).select_related("wo_line"):
        if ln.component_id != ln.wo_line.component_id:
            WorkOrderVariance.objects.create(
                work_order=wo, company=wo.company, kind="SUBSTITUTION", component=ln.component,
                actual_qty=ln.qty, actual_cost=ln.cost_amount,
            )
    residual = money(d(wo.wip_value))
    posted = False
    if residual != 0:
        if posts_to_ledger(wo.company):
            from accounting.services import PostingService

            PostingService.post_mfg_variance(
                company=wo.company, source_type="MFG_CLOSE", source_id=wo.pk, purpose="POST",
                entry_date=doc_date, amount=residual,
                narration=f"{wo.number or wo.pk} closed: cost left in WIP", user=user,
                # What a customer's job work used of our own goods is the cost of the service we bill.
                account_code="5400" if wo.principal_id else "5420",
            )
            posted = True
        wo.cost_variance = money(d(wo.cost_variance) + residual)
        WorkOrderVariance.objects.create(
            work_order=wo, company=wo.company, kind="RESIDUAL", variance=residual, posted_to_gl=posted,
        )
    wo.status = WorkOrder.Status.CLOSED
    wo.closed_at = doc_date
    wo.updated_by = user
    wo.save()
    AuditService.log(
        action="mfg.wo.closed", company=wo.company, user=user, entity_type="WorkOrder",
        entity_id=str(wo.pk), description=f"{wo.number} closed; residual {residual}",
    )
    return wo


@transaction.atomic
def reopen_work_order(wo, user, reason) -> WorkOrder:
    wo = lock_work_order(wo)
    if wo.status != WorkOrder.Status.CLOSED:
        raise rule("Only a closed work order can be reopened.", "MFG_BAD_WO_STATUS")
    if not (reason or "").strip():
        raise rule("Say why the work order is being reopened.", "MFG_REASON_REQUIRED")
    assert_doc_date(wo.company, wo.closed_at, allow_soft_closed=True, label="Reopen")
    residual = sum((v.variance for v in wo.variances.filter(kind="RESIDUAL")), ZERO)
    if posts_to_ledger(wo.company):
        from accounting.services import PostingService

        PostingService.reverse_mfg_document(
            company=wo.company, source_type="MFG_CLOSE", source_id=wo.pk, user=user, entry_date=wo.closed_at,
        )
    wo.cost_variance = money(d(wo.cost_variance) - d(residual))
    wo.variances.all().delete()
    wo.status = WorkOrder.Status.COMPLETED
    wo.closed_at = None
    wo.updated_by = user
    wo.save()
    AuditService.log(
        action="mfg.wo.reopened", company=wo.company, user=user, entity_type="WorkOrder",
        entity_id=str(wo.pk), description=f"{wo.number} reopened: {reason[:200]}",
    )
    return wo
