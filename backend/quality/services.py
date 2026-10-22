"""Inspections, batch holds, non-conformances, supplier scorecard (MFG-20..23)."""

from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.services.audit import AuditService
from core.services.sequences import next_number
from inventory.aux_warehouses import ensure_aux_warehouse
from inventory.models import BatchLot, MovementType, StockBalance, Warehouse
from inventory.services import InventoryService

from .models import (
    Inspection, InspectionParameter, InspectionResult, InspectionTemplate, NonConformance,
)

ZERO = Decimal("0")


def d(v) -> Decimal:
    return Decimal(str(v if v is not None else 0))


def rule(message, code):
    return BusinessRuleError(message, code=code)


# --- templates and inspections -----------------------------------------------------------------

def find_template(company, product, stage):
    """The product's own active template for the stage, else the generic one for the stage."""
    qs = InspectionTemplate.objects.filter(company=company, stage=stage, is_active=True)
    return qs.filter(product=product).order_by("-id").first() or qs.filter(product__isnull=True).order_by("-id").first()


@transaction.atomic
def create_inspection(company, user, *, product, qty, source_type, stage, template=None, batch=None,
                      grn_item=None, receipt_id=None, supplier=None, notes="", inspected_on=None) -> Inspection:
    template = template or find_template(company, product, stage)
    insp = Inspection.objects.create(
        company=company, number=next_number(company, "quality_inspection", prefix="QI"), template=template,
        template_name=template.name if template else "", stage=stage, source_type=source_type, product=product,
        batch=batch, grn_item=grn_item, receipt_id=receipt_id, supplier=supplier, qty_inspected=d(qty),
        notes=notes[:500], inspector=user, inspected_on=inspected_on or timezone.localdate(),
        created_by=user, updated_by=user,
    )
    if template is not None:
        InspectionResult.objects.bulk_create([
            InspectionResult(
                inspection=insp, company=company, name=p.name, kind=p.kind, min_value=p.min_value,
                max_value=p.max_value, unit=p.unit, mandatory=p.mandatory, sequence=p.sequence,
            )
            for p in template.parameters.all()
        ])
    return insp


def _evaluate(result: InspectionResult):
    """Set ``passed`` from the recorded value. Text results are not judged."""
    if result.kind == InspectionParameter.Kind.NUMERIC:
        if result.value_numeric is None:
            result.passed = None
            return
        v = result.value_numeric
        ok = (result.min_value is None or v >= result.min_value) and (result.max_value is None or v <= result.max_value)
        result.passed = ok
    elif result.kind == InspectionParameter.Kind.PASS_FAIL:
        text = (result.value_text or "").strip().lower()
        if not text:
            result.passed = None
        else:
            result.passed = text in ("pass", "passed", "ok", "yes", "true", "1")
    else:
        result.passed = None


@transaction.atomic
def record_results(inspection: Inspection, user, values: dict) -> Inspection:
    """``values`` maps a result id to a number (NUMERIC) or text. Judges each against its limits."""
    insp = Inspection.objects.select_for_update().get(pk=inspection.pk)
    if insp.status != Inspection.Status.DRAFT:
        raise rule("This inspection is already finished.", "QC_NOT_DRAFT")
    by_id = {r.pk: r for r in insp.results.all()}
    for key, value in values.items():
        res = by_id.get(int(key))
        if res is None:
            raise rule("That result does not belong to this inspection.", "QC_BAD_RESULT")
        if res.kind == InspectionParameter.Kind.NUMERIC:
            try:
                res.value_numeric = None if value in (None, "") else Decimal(str(value))
            except Exception:
                raise rule(f"'{res.name}' needs a number.", "QC_BAD_RESULT")
            if res.value_numeric is not None and not res.value_numeric.is_finite():
                raise rule(f"'{res.name}' needs a number.", "QC_BAD_RESULT")
        else:
            res.value_text = "" if value is None else str(value)[:255]
        _evaluate(res)
        res.save(update_fields=["value_numeric", "value_text", "passed"])
    insp.updated_by = user
    insp.save(update_fields=["updated_at", "updated_by"])
    return insp


# --- batch status ----------------------------------------------------------------------------

def set_batch_status(batch: BatchLot, status: str, user, reason: str = "") -> BatchLot:
    if status not in BatchLot.QualityStatus.values:
        raise rule("Unknown batch status.", "QC_BAD_STATUS")
    before = batch.quality_status
    if before == status:
        return batch
    BatchLot.objects.filter(pk=batch.pk).update(quality_status=status, updated_at=timezone.now())
    batch.quality_status = status
    AuditService.log(
        action="quality.batch.status", company=batch.company, user=user, entity_type="BatchLot",
        entity_id=str(batch.pk), description=f"{batch.batch_no}: {before} to {status}. {reason}"[:250],
    )
    return batch


def _move(company, user, product, batch, qty, src, dst, reference_id, reason):
    """Move stock between godowns at the cost it leaves with (a transfer pair that bypasses the hold)."""
    out = InventoryService.post_movement(
        company=company, product=product, warehouse=src, batch=batch, movement_type=MovementType.TRANSFER_OUT,
        quantity=qty, unit_cost=None, user=user, reference_type="quality_move", reference_id=str(reference_id),
        reason=reason[:255], allow_held=True,
    )
    InventoryService.post_movement(
        company=company, product=product, warehouse=dst, batch=batch, movement_type=MovementType.TRANSFER_IN,
        quantity=qty, unit_cost=out.unit_cost, user=user, reference_type="quality_move",
        reference_id=str(reference_id), reason=reason[:255], allow_held=True,
    )


def _scrap_godown(company):
    return ensure_aux_warehouse(company, "SCRAP")


def _rm_godown(company):
    # The one place quality reads manufacturing's settings: which godown released raw material goes to.
    from manufacturing.services.common import get_settings

    return get_settings(company).rm_warehouse or InventoryService.default_warehouse(company)


def _held_qty(company, product, batch, godown_kind):
    agg = StockBalance.objects.filter(
        company=company, product=product, batch=batch, warehouse__kind=godown_kind,
    ).aggregate(t=Sum("on_hand"))
    return d(agg["t"])


# --- deciding --------------------------------------------------------------------------------

def _auto_decision(insp: Inspection) -> str:
    results = list(insp.results.all())
    for r in results:
        if r.mandatory and r.passed is None and r.kind != InspectionParameter.Kind.TEXT:
            raise rule(f"Record '{r.name}' before deciding.", "QC_INCOMPLETE")
        if r.mandatory and r.kind == InspectionParameter.Kind.TEXT and not r.value_text.strip():
            raise rule(f"Record '{r.name}' before deciding.", "QC_INCOMPLETE")
    return "FAIL" if any(r.passed is False for r in results) else "PASS"


@transaction.atomic
def complete_inspection(inspection: Inspection, user, *, decision=None, qty_accepted=None, is_manager=False,
                        notes="") -> Inspection:
    insp = Inspection.objects.select_for_update().get(pk=inspection.pk)
    if insp.status != Inspection.Status.DRAFT:
        raise rule("This inspection is already finished.", "QC_NOT_DRAFT")
    auto = _auto_decision(insp)
    decision = decision or auto
    if decision not in ("PASS", "FAIL", "HOLD", "REWORK"):
        raise rule("Decision must be pass, fail, hold or rework.", "QC_BAD_DECISION")
    if decision == "PASS" and auto == "FAIL" and not is_manager:
        raise rule("A result is outside its limits. Only a manager can pass this.", "QC_PASS_NEEDS_MANAGER")
    total = d(insp.qty_inspected)
    accepted = d(qty_accepted) if qty_accepted is not None else (total if decision == "PASS" else ZERO)
    if accepted < 0 or accepted > total:
        raise rule("Accepted quantity must be between zero and the quantity inspected.", "QC_BAD_QTY")
    if decision in ("HOLD", "REWORK", "FAIL"):
        accepted = ZERO          # a failed lot goes to scrap whole, so nothing of it is "accepted"
    rejected = (total - accepted) if decision in ("PASS", "FAIL") else ZERO
    insp.decision, insp.qty_accepted, insp.qty_rejected = decision, accepted, rejected
    insp.status = Inspection.Status.COMPLETED
    insp.decided_at = timezone.now()
    insp.notes = (notes or insp.notes)[:500]
    insp.updated_by = user
    insp.save()
    _apply(insp, user)
    AuditService.log(
        action="quality.inspection.completed", company=insp.company, user=user, entity_type="Inspection",
        entity_id=str(insp.pk), description=f"{insp.number}: {decision}, accepted {accepted} of {total}",
    )
    return insp


def _apply(insp: Inspection, user):
    decision = insp.decision
    if insp.source_type == Inspection.Source.GRN_ITEM and insp.grn_item_id:
        item = insp.grn_item
        if item.goods_receipt.status != "DRAFT":
            raise rule("The goods receipt is already completed; inspect the batch in stock instead.", "QC_GRN_DONE")
        if decision in ("PASS", "FAIL"):
            received = d(item.quantity_received)
            accepted = min(d(insp.qty_accepted), received)
            item.quantity_accepted, item.quantity_rejected = accepted, received - accepted
            item.save(update_fields=["quantity_accepted", "quantity_rejected", "updated_at"])
        if decision in ("FAIL", "REWORK") or d(insp.qty_rejected) > 0:
            raise_ncr(insp, user, source="GRN")
    elif insp.source_type == Inspection.Source.BATCH and insp.batch_id:
        batch, company = insp.batch, insp.company
        if decision == "PASS":
            held = _held_qty(company, insp.product, batch, "QUARANTINE")
            to_rm = min(d(insp.qty_accepted), held)
            to_scrap = min(max(ZERO, held - to_rm), d(insp.qty_rejected))
            for wh in Warehouse.objects.filter(company=company, kind="QUARANTINE"):
                bal = StockBalance.objects.filter(company=company, product=insp.product, batch=batch, warehouse=wh).first()
                if bal is None or bal.on_hand <= 0:
                    continue
                if to_rm > 0:
                    take = min(to_rm, bal.on_hand)
                    _move(company, user, insp.product, batch, take, wh, _rm_godown(company), insp.pk, f"{insp.number} passed")
                    to_rm -= take
                    bal.refresh_from_db()
                if to_scrap > 0 and bal.on_hand > 0:
                    take = min(to_scrap, bal.on_hand)
                    _move(company, user, insp.product, batch, take, wh, _scrap_godown(company), insp.pk, f"{insp.number} rejected part")
                    to_scrap -= take
            set_batch_status(batch, "RELEASED", user, insp.number)
            if d(insp.qty_rejected) > 0:
                raise_ncr(insp, user, source="INSPECTION")
        elif decision == "FAIL":
            for wh in Warehouse.objects.filter(company=company, kind="QUARANTINE"):
                bal = StockBalance.objects.filter(company=company, product=insp.product, batch=batch, warehouse=wh).first()
                if bal is not None and bal.on_hand > 0:
                    _move(company, user, insp.product, batch, bal.on_hand, wh, _scrap_godown(company), insp.pk, f"{insp.number} failed")
            set_batch_status(batch, "REJECTED", user, insp.number)
            raise_ncr(insp, user, source="INSPECTION")
        else:
            set_batch_status(batch, "HOLD", user, insp.number)
            if decision == "REWORK":
                raise_ncr(insp, user, source="INSPECTION")
    elif insp.source_type == Inspection.Source.RECEIPT and insp.batch_id:
        status = {"PASS": "RELEASED", "FAIL": "REJECTED"}.get(decision, "HOLD")
        set_batch_status(insp.batch, status, user, insp.number)
        if decision in ("FAIL", "REWORK"):
            raise_ncr(insp, user, source="INSPECTION")


@transaction.atomic
def cancel_inspection(inspection: Inspection, user) -> Inspection:
    insp = Inspection.objects.select_for_update().get(pk=inspection.pk)
    if insp.status != Inspection.Status.DRAFT:
        raise rule("Only a draft inspection can be cancelled.", "QC_NOT_DRAFT")
    insp.status = Inspection.Status.CANCELLED
    insp.updated_by = user
    insp.save(update_fields=["status", "updated_at", "updated_by"])
    # A lot held only for this inspection goes back into use.
    if insp.batch_id and insp.batch.quality_status == "HOLD" and not Inspection.objects.filter(
        batch=insp.batch, status=Inspection.Status.DRAFT,
    ).exists():
        set_batch_status(insp.batch, "RELEASED", user, f"{insp.number} cancelled")
    return insp


# --- non-conformance -------------------------------------------------------------------------

def raise_ncr(insp: Inspection, user, *, source="INSPECTION") -> NonConformance:
    existing = NonConformance.objects.filter(company=insp.company, inspection=insp).first()
    if existing:
        return existing
    ncr = NonConformance.objects.create(
        company=insp.company, number=next_number(insp.company, "quality_ncr", prefix="NCR"), source_type=source,
        inspection=insp, product=insp.product, batch=insp.batch, supplier=insp.supplier,
        qty=d(insp.qty_rejected) or d(insp.qty_inspected),
        description=f"{insp.number} {insp.decision.lower()}: {insp.notes}".strip()[:1000],
        created_by=user, updated_by=user,
    )
    return ncr


@transaction.atomic
def advance_ncr(ncr: NonConformance, user, *, status=None, **fields) -> NonConformance:
    """Edit the NCR's fields and move it forward: OPEN, ACTION, VERIFIED, CLOSED."""
    ncr = NonConformance.objects.select_for_update().get(pk=ncr.pk)
    for key in ("root_cause", "action_taken", "preventive_action", "description", "due_date", "owner", "defect_code"):
        if key in fields:
            setattr(ncr, key, fields[key])
    order = ["OPEN", "ACTION", "VERIFIED", "CLOSED"]
    if status and status != ncr.status:
        if status not in order or order.index(status) != order.index(ncr.status) + 1:
            raise rule("A non-conformance moves one step at a time: open, action, verified, closed.", "QC_NCR_ORDER")
        if status == "ACTION" and not (ncr.root_cause or "").strip():
            raise rule("Record the root cause before action starts.", "QC_NCR_NEEDS_CAUSE")
        if status == "VERIFIED" and not (ncr.action_taken or "").strip():
            raise rule("Record the action taken before verifying it.", "QC_NCR_NEEDS_ACTION")
        ncr.status = status
        if status == "CLOSED":
            ncr.closed_at = timezone.now()
    ncr.updated_by = user
    ncr.save()
    AuditService.log(
        action="quality.ncr.updated", company=ncr.company, user=user, entity_type="NonConformance",
        entity_id=str(ncr.pk), description=f"{ncr.number} is {ncr.status}",
    )
    return ncr


# --- supplier scorecard ------------------------------------------------------------------------

def supplier_scorecard(company, date_from=None, date_to=None):
    """Per supplier: lines received, rejection %, on-time %, average lead days, open NCRs."""
    from purchases.models import GoodsReceipt, GoodsReceiptItem

    items = GoodsReceiptItem.objects.filter(
        goods_receipt__company=company, goods_receipt__status=GoodsReceipt.Status.COMPLETED,
    ).select_related("goods_receipt", "goods_receipt__purchase_order", "goods_receipt__supplier")
    if date_from:
        items = items.filter(goods_receipt__receipt_date__gte=date_from)
    if date_to:
        items = items.filter(goods_receipt__receipt_date__lte=date_to)
    stats = defaultdict(lambda: {"received": ZERO, "rejected": ZERO, "grns": set(), "on_time": 0, "timed": 0, "lead": []})
    for it in items:
        grn = it.goods_receipt
        s = stats[grn.supplier_id]
        s["name"] = grn.supplier.name
        s["received"] += d(it.quantity_received)
        s["rejected"] += d(it.quantity_rejected)
        if grn.pk not in s["grns"]:
            s["grns"].add(grn.pk)
            po = grn.purchase_order
            if po is not None:
                s["lead"].append((grn.receipt_date - po.order_date).days)
                if po.expected_delivery:
                    s["timed"] += 1
                    s["on_time"] += 1 if grn.receipt_date <= po.expected_delivery else 0
    open_ncr = defaultdict(int)
    for row in NonConformance.objects.filter(company=company).exclude(status="CLOSED").values("supplier_id"):
        open_ncr[row["supplier_id"]] += 1
    out = []
    for sid, s in stats.items():
        out.append({
            "supplier": sid, "name": s["name"], "receipts": len(s["grns"]), "received_qty": s["received"],
            "rejected_qty": s["rejected"],
            "rejection_pct": (s["rejected"] * 100 / s["received"]).quantize(Decimal("0.1")) if s["received"] else ZERO,
            "on_time_pct": (Decimal(s["on_time"]) * 100 / s["timed"]).quantize(Decimal("0.1")) if s["timed"] else None,
            "avg_lead_days": (Decimal(sum(s["lead"])) / len(s["lead"])).quantize(Decimal("0.1")) if s["lead"] else None,
            "open_ncrs": open_ncr.get(sid, 0),
        })
    return sorted(out, key=lambda r: (-r["rejection_pct"], r["name"]))
