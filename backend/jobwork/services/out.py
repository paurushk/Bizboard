"""Job work OUT: our material goes to a job worker and comes back changed (MFG-24)."""

from accounting.books import posts_to_ledger
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core.services.audit import AuditService
from inventory.models import BatchLot, MovementType, StockMovement, Warehouse
from inventory.services import InventoryService
from masters.models import Product, Supplier

from jobwork.models import (
    JobWorkChallan, JobWorkChallanLine, JobWorkOrder, JobWorkReceipt, JobWorkReceiptLine, JobWorkSettlement,
)

from . import common
from .common import ZERO, d, money, rule

REF = "jobwork_challan"
REF_REV = "jobwork_challan_reverse"
REF_RCPT = "jobwork_receipt"


def _doc_date(company, when, *, allow_soft_closed=False, can_backdate=True, label="Document"):
    from manufacturing.services.common import assert_doc_date

    return assert_doc_date(company, when, allow_soft_closed=allow_soft_closed, can_backdate=can_backdate, label=label)


def _fk(model, company, value):
    if value in (None, ""):
        return None
    if isinstance(value, model):
        if value.company_id != company.id:
            raise rule("That record belongs to another company.", "JW_BAD_REFERENCE")
        return value
    found = model.objects.filter(pk=value, company=company).first()
    if found is None:
        raise rule("That record was not found.", "JW_BAD_REFERENCE")
    return found


# --- orders ----------------------------------------------------------------------------------

@transaction.atomic
def create_order(company, user, *, supplier, process="", expected_return_date=None, notes="",
                 direct_supply_declared=False) -> JobWorkOrder:
    supplier = _fk(Supplier, company, supplier)
    if supplier is None:
        raise rule("Choose the job worker.", "JW_BAD_REFERENCE")
    order = JobWorkOrder.objects.create(
        company=company, direction=JobWorkOrder.Direction.OUT, supplier=supplier,
        number=common.number(company, "jobwork_order", "JWO"), process=process[:200],
        expected_return_date=expected_return_date, notes=notes[:500],
        direct_supply_declared=direct_supply_declared,
        job_worker_warehouse=common.ensure_job_worker_warehouse(company, supplier),
        created_by=user, updated_by=user,
    )
    AuditService.log(
        action="jobwork.order.created", company=company, user=user, entity_type="JobWorkOrder",
        entity_id=str(order.pk), description=f"{order.number} to {supplier.name}",
    )
    return order


def _open_order(order: JobWorkOrder) -> JobWorkOrder:
    order = JobWorkOrder.objects.select_for_update().get(pk=order.pk)
    if order.direction != JobWorkOrder.Direction.OUT:
        raise rule("This is a job work order for a customer's material.", "JW_WRONG_DIRECTION")
    if order.status != JobWorkOrder.Status.OPEN:
        raise rule("This job work order is closed.", "JW_ORDER_CLOSED")
    return order


# --- challan (send) --------------------------------------------------------------------------

@transaction.atomic
def create_challan(order, user, lines, *, challan_date=None, warehouse=None, vehicle_no="", notes="",
                   origin=JobWorkChallan.Origin.OWN_PREMISES) -> JobWorkChallan:
    order = _open_order(order)
    company = order.company
    if not lines:
        raise rule("A challan needs at least one line.", "JW_EMPTY_DOC")
    ch = JobWorkChallan.objects.create(
        company=company, order=order, challan_date=challan_date or timezone.localdate(),
        warehouse=_fk(Warehouse, company, warehouse), vehicle_no=vehicle_no[:20], notes=notes[:500],
        origin=origin, created_by=user, updated_by=user,
    )
    for ln in lines:
        product = _fk(Product, company, ln.get("product"))
        if product is None:
            raise rule("Each line needs a product.", "JW_BAD_REFERENCE")
        qty = d(ln.get("qty"))
        if qty <= 0:
            raise rule("Quantity must be above zero.", "JW_BAD_QTY")
        JobWorkChallanLine.objects.create(
            challan=ch, company=company, product=product, qty=qty,
            batch=_fk(BatchLot, company, ln.get("batch")),
            goods_kind=ln.get("goods_kind") or JobWorkChallanLine.GoodsKind.INPUT,
            serial_numbers=list(ln.get("serial_numbers") or []),
        )
    return ch


@transaction.atomic
def issue_challan(challan, user, *, can_backdate=True) -> JobWorkChallan:
    """Send the goods: out of our godown, into the job worker's, carrying their cost with them."""
    ch = JobWorkChallan.objects.select_for_update().get(pk=challan.pk)
    order = _open_order(ch.order)
    if ch.status != JobWorkChallan.Status.DRAFT:
        raise rule("This challan has already been issued.", "JW_DOC_NOT_DRAFT")
    company = ch.company
    when = _doc_date(company, ch.challan_date, can_backdate=can_backdate, label="Challan")
    src = ch.warehouse or InventoryService.default_warehouse(company)
    dst = order.job_worker_warehouse
    for ln in ch.lines.select_related("product", "batch").order_by("id"):
        out = InventoryService.post_movement(
            company=company, product=ln.product, warehouse=src, batch=ln.batch,
            movement_type=MovementType.TRANSFER_OUT, quantity=ln.qty, unit_cost=None, user=user,
            reference_type=REF, reference_id=str(ch.pk), movement_date=when,
        )
        # The transfer carries the cost the stock left with, never nil.
        inbound = InventoryService.post_movement(
            company=company, product=ln.product, warehouse=dst, batch=ln.batch,
            movement_type=MovementType.TRANSFER_IN, quantity=ln.qty, unit_cost=out.unit_cost, user=user,
            reference_type=REF, reference_id=str(ch.pk), movement_date=when,
        )
        if ln.product.track_serial:
            common.move_serials(company, ln.product, ln.serial_numbers, src, dst)
        ln.unit_cost = out.unit_cost
        ln.movement_ids = [out.pk, inbound.pk]
        ln.save(update_fields=["unit_cost", "movement_ids"])
    ch.status = JobWorkChallan.Status.ISSUED
    ch.number = common.number(company, "jobwork_challan", "JWC")
    ch.challan_date = when
    ch.posted_at = timezone.now()
    ch.updated_by = user
    ch.save()
    AuditService.log(
        action="jobwork.challan.issued", company=company, user=user, entity_type="JobWorkChallan",
        entity_id=str(ch.pk), description=f"{ch.number} to {order.supplier.name}",
    )
    if order.work_order_id:
        from manufacturing.services import subcontract

        subcontract.on_challan_issued(order)
    return ch


@transaction.atomic
def register_direct_receipt(grn, user):
    """A goods receipt into a job worker's godown: the supplier shipped straight there.

    The stock is already in the job worker's godown. This writes the challan that lets the
    sending be settled, aged and reported (ITC-04 table 4, "sent directly from supplier").
    """
    wh = grn.warehouse
    if wh is None or wh.kind != Warehouse.Kind.JOB_WORKER or wh.job_worker_id is None:
        return None
    company = grn.company
    order = JobWorkOrder.objects.filter(
        company=company, direction=JobWorkOrder.Direction.OUT, supplier_id=wh.job_worker_id,
        status=JobWorkOrder.Status.OPEN,
    ).order_by("-id").first()
    if order is None:
        order = create_order(company, user, supplier=wh.job_worker, process="Sent directly from supplier")
    ch = JobWorkChallan.objects.create(
        company=company, order=order, challan_date=grn.receipt_date, status=JobWorkChallan.Status.ISSUED,
        origin=JobWorkChallan.Origin.DIRECT_FROM_SUPPLIER, supplier_invoice_ref=grn.number,
        number=common.number(company, "jobwork_challan", "JWC"), posted_at=timezone.now(),
        notes=f"Goods receipt {grn.number} from {grn.supplier.name}", created_by=user, updated_by=user,
    )
    for item in grn.items.select_related("product", "batch"):
        accepted = d(item.quantity_accepted)
        if accepted <= 0:
            continue
        JobWorkChallanLine.objects.create(
            challan=ch, company=company, product=item.product, qty=accepted, batch=item.batch,
            unit_cost=item.unit_price or item.product.purchase_price,
        )
    return ch


@transaction.atomic
def reverse_challan(challan, user, reason) -> JobWorkChallan:
    ch = JobWorkChallan.objects.select_for_update().get(pk=challan.pk)
    if ch.status != JobWorkChallan.Status.ISSUED:
        raise rule("Only an issued challan can be reversed.", "JW_DOC_NOT_POSTED")
    if not (reason or "").strip():
        raise rule("Say why the challan is being reversed.", "JW_REASON_REQUIRED")
    if ch.origin != JobWorkChallan.Origin.OWN_PREMISES and ch.origin != JobWorkChallan.Origin.FROM_OTHER_JOB_WORKER:
        raise rule("A challan raised from a goods receipt is reversed by cancelling that receipt.", "JW_REVERSAL_ORDER")
    lines = list(ch.lines.select_related("product", "batch"))
    if any(ln.qty_settled > 0 for ln in lines) or ch.onward_challans.filter(status="ISSUED").exists():
        raise rule("The job worker has already accounted for part of this. Reverse that first.", "JW_REVERSAL_ORDER")
    company = ch.company
    when = _doc_date(company, ch.challan_date, allow_soft_closed=True, label="Reversal")
    for ln in lines:
        out_id, in_id = ln.movement_ids
        out_mv = StockMovement.objects.select_related("warehouse", "batch", "product").get(pk=out_id)
        in_mv = StockMovement.objects.select_related("warehouse", "batch", "product").get(pk=in_id)
        if InventoryService.available_quantity(company, ln.product, in_mv.warehouse, ln.batch) < ln.qty:
            raise rule("The goods are no longer at the job worker.", "JW_REVERSAL_ORDER")
        InventoryService.post_movement(
            company=company, product=ln.product, warehouse=in_mv.warehouse, batch=ln.batch,
            movement_type=MovementType.MANUFACTURE_REVERSAL, quantity=-ln.qty, unit_cost=in_mv.unit_cost, user=user,
            reference_type=REF_REV, reference_id=str(ch.pk), movement_date=when, reason=reason[:255],
        )
        InventoryService.retire_source_layers(in_mv, ln.qty)
        back = InventoryService.post_movement(
            company=company, product=ln.product, warehouse=out_mv.warehouse, batch=ln.batch,
            movement_type=MovementType.MANUFACTURE_REVERSAL, quantity=ln.qty, unit_cost=out_mv.unit_cost, user=user,
            reference_type=REF_REV, reference_id=str(ch.pk), movement_date=when, reason=reason[:255],
        )
        InventoryService.restore_fifo_peels(out_mv, back)
        if ln.product.track_serial:
            common.move_serials(company, ln.product, ln.serial_numbers, in_mv.warehouse, out_mv.warehouse)
    ch.status = JobWorkChallan.Status.REVERSED
    ch.reversed_at = timezone.now()
    ch.reverse_reason = reason[:500]
    ch.updated_by = user
    ch.save()
    AuditService.log(
        action="jobwork.challan.reversed", company=company, user=user, entity_type="JobWorkChallan",
        entity_id=str(ch.pk), description=f"{ch.number}: {reason[:200]}",
    )
    return ch


# --- receipt (what comes back) -----------------------------------------------------------------

K = JobWorkReceiptLine.Kind


@transaction.atomic
def create_receipt(order, user, lines, *, receipt_date=None, warehouse=None, notes="") -> JobWorkReceipt:
    order = _open_order(order)
    company = order.company
    if not lines:
        raise rule("A receipt needs at least one line.", "JW_EMPTY_DOC")
    rc = JobWorkReceipt.objects.create(
        company=company, order=order, receipt_date=receipt_date or timezone.localdate(),
        warehouse=_fk(Warehouse, company, warehouse), notes=notes[:500], created_by=user, updated_by=user,
    )
    for ln in lines:
        kind = ln.get("kind")
        if kind not in K.values:
            raise rule("Unknown receipt line type.", "JW_BAD_KIND")
        product = _fk(Product, company, ln.get("product") or ln.get("input_product"))
        if product is None:
            raise rule("Each line needs a product.", "JW_BAD_REFERENCE")
        qty = d(ln.get("qty"))
        input_product = _fk(Product, company, ln.get("input_product"))
        input_qty = d(ln.get("input_qty"))
        if d(ln.get("charge_amount")) < 0 or d(ln.get("loss_qty")) < 0 or d(ln.get("unit_cost")) < 0 or input_qty < 0:
            raise rule("Charges, losses, rates and quantities cannot be negative.", "JW_BAD_QTY")
        if kind in (K.PROCESSED, K.UNPROCESSED_RETURN, K.SENT_TO_OTHER, K.SUPPLIED_FROM_JW, K.SCRAP_RETAINED) \
                and (input_product or product) is None:
            raise rule("Say which sent material this accounts for.", "JW_BAD_REFERENCE")
        if kind == K.PROCESSED and (input_qty <= 0 or qty <= 0 or input_product is None):
            raise rule("Processed goods need the quantity back and the material used.", "JW_BAD_QTY")
        if qty <= 0 and kind != K.PROCESSED:
            raise rule("Quantity must be above zero.", "JW_BAD_QTY")
        JobWorkReceiptLine.objects.create(
            receipt=rc, company=company, kind=kind, product=product, qty=qty,
            batch=_fk(BatchLot, company, ln.get("batch")), input_product=input_product, input_qty=input_qty,
            input_batch=_fk(BatchLot, company, ln.get("input_batch")),
            charge_amount=d(ln.get("charge_amount")), unit_cost=ln.get("unit_cost"),
            other_order=_fk(JobWorkOrder, company, ln.get("other_order")), invoice_ref=(ln.get("invoice_ref") or "")[:64],
            loss_qty=d(ln.get("loss_qty")),
        )
    return rc


def _settle(company, order, product, qty, batch, receipt_line, when):
    """Account for ``qty`` of ``product`` against the oldest open challan lines. Returns [(line, take)]."""
    qs = JobWorkChallanLine.objects.select_for_update(of=("self",)).filter(
        challan__order=order, challan__status=JobWorkChallan.Status.ISSUED, product=product,
    ).select_related("challan").order_by("challan__challan_date", "id")
    if batch is not None:
        qs = qs.filter(batch=batch)
    remaining, taken = d(qty), []
    for cl in qs:
        if remaining <= 0:
            break
        take = min(remaining, cl.qty_open)
        if take <= 0:
            continue
        JobWorkSettlement.objects.create(
            receipt_line=receipt_line, challan_line=cl, company=company, qty=take, settled_on=when,
        )
        cl.qty_settled = cl.qty_settled + take
        cl.save(update_fields=["qty_settled"])
        taken.append((cl, take))
        remaining -= take
    if remaining > 0:
        raise rule(
            f"{remaining} of '{product.name}' was never sent to this job worker, or has already been accounted for.",
            "JW_OVER_RETURN",
        )
    return taken


def _transfer(company, user, product, batch, qty, src, dst, unit_cost_hint, reference, when, ref_type):
    out = InventoryService.post_movement(
        company=company, product=product, warehouse=src, batch=batch, movement_type=MovementType.TRANSFER_OUT,
        quantity=qty, unit_cost=unit_cost_hint, user=user, reference_type=ref_type, reference_id=str(reference),
        movement_date=when,
    )
    inbound = InventoryService.post_movement(
        company=company, product=product, warehouse=dst, batch=batch, movement_type=MovementType.TRANSFER_IN,
        quantity=qty, unit_cost=out.unit_cost, user=user, reference_type=ref_type, reference_id=str(reference),
        movement_date=when,
    )
    return out, inbound


@transaction.atomic
def post_receipt(receipt, user, *, can_backdate=True) -> JobWorkReceipt:
    rc = JobWorkReceipt.objects.select_for_update().get(pk=receipt.pk)
    order = _open_order(rc.order)
    if rc.status != JobWorkReceipt.Status.DRAFT:
        raise rule("This receipt has already been posted.", "JW_DOC_NOT_DRAFT")
    company = rc.company
    when = _doc_date(company, rc.receipt_date, can_backdate=can_backdate, label="Receipt")
    jw = order.job_worker_warehouse
    own = rc.warehouse or InventoryService.default_warehouse(company)
    lines = list(rc.lines.select_related("product", "input_product", "batch", "input_batch", "other_order"))

    # Pass 1: account for the material and take it out of the job worker's godown.
    consumed_cost: dict[int, Decimal] = {}
    recovery_total = ZERO
    absorbed = ZERO
    loss_total = ZERO
    for ln in lines:
        src_product = ln.input_product or ln.product
        if ln.kind == K.SCRAP_RETURNED:
            continue
        need = ln.input_qty if ln.kind == K.PROCESSED else ln.qty
        taken = _settle(company, order, src_product, need, ln.input_batch, ln, when)
        ids, cost = [], ZERO
        for cl, take in taken:
            if ln.kind == K.PROCESSED:
                mv = InventoryService.post_movement(
                    company=company, product=src_product, warehouse=jw, batch=cl.batch,
                    movement_type=MovementType.MANUFACTURE_ISSUE, quantity=take, unit_cost=cl.unit_cost, user=user,
                    reference_type=REF_RCPT, reference_id=str(rc.pk), movement_date=when,
                )
                ids.append(mv.pk)
                cost += take * d(mv.unit_cost)
            elif ln.kind == K.UNPROCESSED_RETURN:
                out, inb = _transfer(company, user, src_product, cl.batch, take, jw, own, cl.unit_cost, rc.pk, when, REF_RCPT)
                ids += [out.pk, inb.pk]
                cost += take * d(out.unit_cost)
            elif ln.kind == K.SCRAP_RETAINED:
                mv = InventoryService.post_movement(
                    company=company, product=src_product, warehouse=jw, batch=cl.batch,
                    movement_type=MovementType.ADJUSTMENT, quantity=-take, unit_cost=cl.unit_cost, user=user,
                    reference_type="jobwork_scrap_retained", reference_id=str(rc.pk), movement_date=when,
                    reason="Scrap kept by the job worker",
                )
                ids.append(mv.pk)
                loss_total += take * d(mv.unit_cost)
                cost += take * d(mv.unit_cost)
            elif ln.kind == K.SENT_TO_OTHER:
                if ln.other_order_id is None:
                    raise rule("Say which job worker it went on to.", "JW_BAD_REFERENCE")
                if ln.other_order.direction != JobWorkOrder.Direction.OUT or ln.other_order.status != "OPEN":
                    raise rule("The other job work order is not open.", "JW_ORDER_CLOSED")
                out, inb = _transfer(
                    company, user, src_product, cl.batch, take, jw, ln.other_order.job_worker_warehouse,
                    cl.unit_cost, rc.pk, when, REF_RCPT,
                )
                ids += [out.pk, inb.pk]
                cost += take * d(out.unit_cost)
            elif ln.kind == K.SUPPLIED_FROM_JW:
                if not order.direct_supply_declared:
                    raise rule(
                        "Supplying straight from the job worker needs their premises declared as ours, or them registered.",
                        "JW_DIRECT_SUPPLY_NOT_DECLARED",
                    )
                if not ln.invoice_ref.strip():
                    raise rule("Give the invoice the goods went out on.", "JW_INVOICE_REQUIRED")
        if ln.kind == K.SENT_TO_OTHER:
            _issue_onward(rc, ln, taken, user, when)
        consumed_cost[ln.pk] = cost
        ln.movement_ids = ids
        ln.cost_amount = money(cost)
        ln.save(update_fields=["movement_ids", "cost_amount"])
    for ln in lines:
        if ln.kind == K.SCRAP_RETURNED:
            rate = d(ln.unit_cost)
            recovery_total += ln.qty * rate
    absorbed = sum((d(ln.charge_amount) for ln in lines if ln.kind == K.PROCESSED), ZERO)

    # Pass 2: receive what came back. Goods cost what was used plus the job charge, less scrap worth keeping.
    processed = [ln for ln in lines if ln.kind == K.PROCESSED]
    pool_base = sum((consumed_cost[ln.pk] for ln in processed), ZERO)
    for ln in lines:
        if ln.kind == K.SCRAP_RETURNED:
            rate = d(ln.unit_cost)
            scrap_wh = _aux(company, "SCRAP")
            mv = InventoryService.post_movement(
                company=company, product=ln.product, warehouse=scrap_wh, batch=ln.batch,
                movement_type=MovementType.MANUFACTURE_RECEIPT, quantity=ln.qty, unit_cost=rate, user=user,
                reference_type=REF_RCPT, reference_id=str(rc.pk), movement_date=when,
            )
            ln.movement_ids = [mv.pk]
            ln.cost_amount = money(ln.qty * rate)
            ln.save(update_fields=["movement_ids", "cost_amount"])
        elif ln.kind == K.PROCESSED:
            share = (consumed_cost[ln.pk] / pool_base) if pool_base else Decimal(1) / len(processed)
            line_pool = consumed_cost[ln.pk] + d(ln.charge_amount) - recovery_total * share
            if line_pool < 0:
                raise rule(
                    f"The scrap returned is worth more than the material and charge for '{ln.product.name}', so the "
                    f"finished goods would have a negative value. Check the scrap rate.",
                    "JW_NEGATIVE_VALUE",
                )
            unit = (line_pool / ln.qty).quantize(Decimal("0.0001"))
            mv = InventoryService.post_movement(
                company=company, product=ln.product, warehouse=own, batch=ln.batch,
                movement_type=MovementType.MANUFACTURE_RECEIPT, quantity=ln.qty, unit_cost=unit, user=user,
                reference_type=REF_RCPT, reference_id=str(rc.pk), movement_date=when,
            )
            ln.movement_ids = list(ln.movement_ids) + [mv.pk]
            ln.unit_cost = unit
            ln.cost_amount = money(unit * ln.qty)
            ln.save(update_fields=["movement_ids", "unit_cost", "cost_amount"])
    rc.status = JobWorkReceipt.Status.POSTED
    rc.number = common.number(company, "jobwork_receipt", "JWR")
    rc.receipt_date = when
    rc.warehouse = own
    rc.posted_at = timezone.now()
    rc.updated_by = user
    rc.save()
    if posts_to_ledger(company):
        from accounting.services import PostingService

        if absorbed > 0:
            PostingService.post_mfg_absorption(
                company=company, source_type="JW_RECEIPT", source_id=rc.pk, purpose="POST", entry_date=when,
                amount=absorbed, narration=f"{rc.number} job charges", user=user, debit_code="1400",
            )
        if loss_total > 0:
            _post_process_loss(company, rc, when, loss_total, user)
    AuditService.log(
        action="jobwork.receipt.posted", company=company, user=user, entity_type="JobWorkReceipt",
        entity_id=str(rc.pk), description=f"{rc.number} from {order.supplier.name}",
    )
    if order.work_order_id:
        from manufacturing.services import subcontract

        subcontract.on_receipt_posted(order, rc, user)
    return rc


def _aux(company, kind):
    from inventory.aux_warehouses import ensure_aux_warehouse

    return ensure_aux_warehouse(company, kind)


def _post_process_loss(company, rc, when, amount, user):
    """Scrap the job worker kept: stock value written off to the scrap and shrinkage loss account."""
    from accounting.models import JournalEntry  # noqa: F401  (ensures the app is loaded)
    from accounting.services import PostingService

    PostingService._ensure_chart(company)
    PostingService.post(
        company=company, source_type="JW_RECEIPT", source_id=rc.pk, purpose="LOSS", entry_date=when, user=user,
        narration=f"{rc.number} scrap kept by job worker",
        lines=[
            {"account": PostingService._account(company, "5450"), "debit": money(amount)},
            {"account": PostingService._account(company, "1400"), "credit": money(amount)},
        ],
    )


def _issue_onward(rc, ln, taken, user, when):
    """Goods passed from one job worker to another need a challan of their own."""
    other = ln.other_order
    ch = JobWorkChallan.objects.create(
        company=rc.company, order=other, challan_date=when, status=JobWorkChallan.Status.ISSUED,
        origin=JobWorkChallan.Origin.FROM_OTHER_JOB_WORKER, source_challan=taken[0][0].challan,
        number=common.number(rc.company, "jobwork_challan", "JWC"), posted_at=timezone.now(),
        notes=f"Passed on from {rc.order.supplier.name} ({rc.pk})", created_by=user, updated_by=user,
    )
    for cl, take in taken:
        JobWorkChallanLine.objects.create(
            challan=ch, company=rc.company, product=cl.product, batch=cl.batch, qty=take,
            goods_kind=cl.goods_kind, unit_cost=cl.unit_cost,
        )
    return ch


@transaction.atomic
def reverse_receipt(receipt, user, reason) -> JobWorkReceipt:
    rc = JobWorkReceipt.objects.select_for_update().get(pk=receipt.pk)
    if rc.status != JobWorkReceipt.Status.POSTED:
        raise rule("Only a posted receipt can be reversed.", "JW_DOC_NOT_POSTED")
    if not (reason or "").strip():
        raise rule("Say why the receipt is being reversed.", "JW_REASON_REQUIRED")
    company = rc.company
    when = _doc_date(company, rc.receipt_date, allow_soft_closed=True, label="Reversal")
    lines = list(rc.lines.select_related("product", "other_order"))
    # Goods passed to another job worker with a challan that has itself been settled cannot be undone.
    for ln in lines:
        if ln.kind == K.SENT_TO_OTHER:
            onward = JobWorkChallan.objects.filter(
                company=company, source_challan__in=[s.challan_line.challan for s in ln.settlements.all()],
                order=ln.other_order, status="ISSUED",
            )
            if JobWorkChallanLine.objects.filter(challan__in=onward, qty_settled__gt=0).exists():
                raise rule("The next job worker has already accounted for these goods. Reverse that first.", "JW_REVERSAL_ORDER")
    for ln in lines:
        for mid in reversed(ln.movement_ids or []):
            mv = StockMovement.objects.select_related("warehouse", "batch", "product").get(pk=mid)
            if mv.quantity > 0:
                if InventoryService.available_quantity(company, mv.product, mv.warehouse, mv.batch) < mv.quantity:
                    raise rule(f"'{mv.product.name}' from this receipt has already been used or sold.", "JW_REVERSAL_ORDER")
                InventoryService.post_movement(
                    company=company, product=mv.product, warehouse=mv.warehouse, batch=mv.batch,
                    movement_type=MovementType.MANUFACTURE_REVERSAL, quantity=-abs(mv.quantity),
                    unit_cost=mv.unit_cost, user=user, reference_type=REF_REV, reference_id=str(rc.pk),
                    movement_date=when, reason=reason[:255],
                )
                InventoryService.retire_source_layers(mv, abs(mv.quantity))
            else:
                back = InventoryService.post_movement(
                    company=company, product=mv.product, warehouse=mv.warehouse, batch=mv.batch,
                    movement_type=MovementType.MANUFACTURE_REVERSAL, quantity=abs(mv.quantity),
                    unit_cost=mv.unit_cost, user=user, reference_type=REF_REV, reference_id=str(rc.pk),
                    movement_date=when, reason=reason[:255],
                )
                InventoryService.restore_fifo_peels(mv, back)
        for st in ln.settlements.filter(reversed=False):
            cl = JobWorkChallanLine.objects.select_for_update().get(pk=st.challan_line_id)
            cl.qty_settled = cl.qty_settled - st.qty
            cl.save(update_fields=["qty_settled"])
            st.reversed = True
            st.save(update_fields=["reversed"])
        if ln.kind == K.SENT_TO_OTHER:
            JobWorkChallan.objects.filter(
                company=company, order=ln.other_order, origin=JobWorkChallan.Origin.FROM_OTHER_JOB_WORKER,
                notes__contains=f"({rc.pk})",
            ).update(status=JobWorkChallan.Status.REVERSED, reversed_at=timezone.now(), reverse_reason=reason[:500])
    if posts_to_ledger(company):
        from accounting.services import PostingService

        PostingService.reverse_mfg_document(company=company, source_type="JW_RECEIPT", source_id=rc.pk, user=user, entry_date=when)
    rc.status = JobWorkReceipt.Status.REVERSED
    rc.reversed_at = timezone.now()
    rc.reversed_by = user
    rc.reverse_reason = reason[:500]
    rc.save()
    AuditService.log(
        action="jobwork.receipt.reversed", company=company, user=user, entity_type="JobWorkReceipt",
        entity_id=str(rc.pk), description=f"{rc.number}: {reason[:200]}",
    )
    if rc.order.work_order_id:
        from manufacturing.services import subcontract

        subcontract.on_receipt_reversed(rc.order, rc)
    return rc


# --- balances and ageing -----------------------------------------------------------------------

def balance_by_job_worker(company):
    """What each job worker still holds of ours: product, open quantity, value."""
    out = []
    lines = (
        JobWorkChallanLine.objects.filter(company=company, challan__status="ISSUED", challan__order__direction="OUT")
        .select_related("challan__order__supplier", "product")
    )
    book: dict[tuple, dict] = {}
    for ln in lines:
        if ln.qty_open <= 0:
            continue
        key = (ln.challan.order.supplier_id, ln.product_id)
        row = book.setdefault(key, {
            "supplier": ln.challan.order.supplier_id, "supplier_name": ln.challan.order.supplier.name,
            "product": ln.product_id, "product_name": ln.product.name, "qty": ZERO, "value": ZERO,
        })
        row["qty"] += ln.qty_open
        row["value"] += ln.qty_open * d(ln.unit_cost)
    for row in book.values():
        row["value"] = money(row["value"])
        out.append(row)
    return sorted(out, key=lambda r: (r["supplier_name"], r["product_name"]))


def ageing(company, as_of: date | None = None):
    """Open sent material with its age and how close it is to counting as a supply (s.143)."""
    as_of = as_of or timezone.localdate()
    cfg = common.settings_for(company)
    rows = []
    lines = (
        JobWorkChallanLine.objects.filter(company=company, challan__status="ISSUED", challan__order__direction="OUT")
        .select_related("challan__order__supplier", "product")
    )
    for ln in lines:
        if ln.qty_open <= 0:
            continue
        capital = ln.goods_kind == JobWorkChallanLine.GoodsKind.CAPITAL_GOOD
        limit = cfg.jw_capital_limit_days if capital else cfg.jw_input_limit_days
        alert = cfg.jw_capital_alert_days if capital else cfg.jw_input_alert_days
        days = (as_of - ln.challan.challan_date).days
        status = "OVERDUE" if days > limit else "ALERT" if days >= alert else "OK"
        rows.append({
            "challan_line": ln.pk, "challan": ln.challan.number, "challan_date": ln.challan.challan_date,
            "supplier": ln.challan.order.supplier.name, "product": ln.product.name, "open_qty": ln.qty_open,
            "value": money(ln.qty_open * d(ln.unit_cost)), "goods_kind": ln.goods_kind, "days": days,
            "limit_days": limit, "due_by": ln.challan.challan_date + timedelta(days=limit), "status": status,
        })
    return sorted(rows, key=lambda r: -r["days"])


@transaction.atomic
def close_order(order, user) -> JobWorkOrder:
    order = JobWorkOrder.objects.select_for_update().get(pk=order.pk)
    if order.status != JobWorkOrder.Status.OPEN:
        raise rule("This job work order is already closed.", "JW_ORDER_CLOSED")
    if order.direction == JobWorkOrder.Direction.IN:
        # A customer's order has no sent-out lines to settle; it can close once none of their material that came
        # in under it is still in our hands.
        from jobwork.models import PrincipalMaterialMovement
        from jobwork.services import principal

        held = [
            pid for pid in PrincipalMaterialMovement.objects.filter(
                company=order.company, order=order, reversed=False,
            ).values_list("product_id", flat=True).distinct()
            if principal.on_hand(order.company, order.customer, pid) > 0
        ]
        if held:
            raise rule(
                "We still hold the customer's material. Return it, or record what was lost, first.", "JW_STILL_HOLDING",
            )
        open_lines = []
    else:
        open_lines = [
            ln for ln in JobWorkChallanLine.objects.filter(challan__order=order, challan__status="ISSUED") if ln.qty_open > 0
        ]
    if open_lines:
        raise rule(
            "The job worker still holds our material. Record what came back, or what became of it, first.",
            "JW_STILL_HOLDING",
        )
    order.status = JobWorkOrder.Status.CLOSED
    order.updated_by = user
    order.save(update_fields=["status", "updated_at", "updated_by"])
    AuditService.log(
        action="jobwork.order.closed", company=order.company, user=user, entity_type="JobWorkOrder",
        entity_id=str(order.pk), description=order.number,
    )
    if order.work_order_id:
        from manufacturing.services import subcontract

        subcontract.on_order_closed(order)
    return order
