"""Production receipt: finished goods, co-products, by-products, scrap, rework (MFG-08, MFG-11)."""

from accounting.books import posts_to_ledger
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core.services.audit import AuditService
from core.services.feature_flags import flag_enabled
from inventory.aux_warehouses import ensure_aux_warehouse
from inventory.models import BatchLot, MovementType, SerialNumber, StockMovement, Warehouse
from inventory.services import InventoryService, SerialNumberService
from masters.models import Product

from manufacturing.models import (
    DocumentStatus, MaterialIssue, ProductionReceipt, ProductionReceiptLine, WorkOrder,
)

from . import reservation, trace
from .common import (
    ZERO, assert_doc_date, cost_receipt, d, get_settings, money, next_number, qty3,
    resolve_receipt_warehouse, rule, unit4,
)
from .issue import (
    _has_other_posted_documents, _resolve_fk, assert_documents_allowed,
    create_issue, lock_work_order, post_issue, reverse_issue,
)

PL = ProductionReceiptLine

ABSORB_ACCOUNT = {"OTHER": "5410", "LABOUR": "5430", "OVERHEAD": "5440", "MACHINE": "5440"}


def _output_batch(wo, product, batch_no, exp, mfg, user, gate_date):
    """Get or create the lot for finished output (same expiry/mfg checks as the one-step flow)."""
    if not product.track_batch:
        return None
    number = batch_no or wo.batch_no or wo.number or f"WO-{wo.pk}"
    batch, created = BatchLot.objects.get_or_create(
        company=wo.company, product=product, batch_no=number,
        defaults={
            "expiry_date": exp or wo.exp_date, "manufacturing_date": mfg or wo.mfg_date or gate_date,
            "created_by": user, "updated_by": user,
        },
    )
    if not created:
        want_exp, want_mfg = exp or wo.exp_date, mfg or wo.mfg_date
        if want_exp and batch.expiry_date and batch.expiry_date != want_exp:
            raise rule(
                f"Batch {number} already exists with expiry {batch.expiry_date}; entered {want_exp} does not match.",
                "MFG_BATCH_MISMATCH",
            )
        if want_mfg and batch.manufacturing_date and batch.manufacturing_date != want_mfg:
            raise rule(
                f"Batch {number} already exists with mfg date {batch.manufacturing_date}; "
                f"entered {want_mfg} does not match.",
                "MFG_BATCH_MISMATCH",
            )
        changed = []
        if want_exp and not batch.expiry_date:
            batch.expiry_date = want_exp
            changed.append("expiry_date")
        if want_mfg and not batch.manufacturing_date:
            batch.manufacturing_date = want_mfg
            changed.append("manufacturing_date")
        if changed:
            batch.save(update_fields=changed + ["updated_at"])
    return batch


def _aux_batch(wo, product, prefix, user):
    if not product.track_batch:
        return None
    batch, _ = BatchLot.objects.get_or_create(
        company=wo.company, product=product, batch_no=f"{prefix}-{wo.number or wo.pk}",
        defaults={"created_by": user, "updated_by": user},
    )
    return batch


# --- drafts ----------------------------------------------------------------------------------

def produced_so_far(wo) -> Decimal:
    return d(wo.qty_completed) + d(wo.qty_rework) + d(wo.qty_rejected)


@transaction.atomic
def create_receipt(wo, user, payload=None) -> ProductionReceipt:
    """A draft receipt. With no lines, it receives what is still planned, with planned outputs scaled."""
    payload = dict(payload or {})
    wo = lock_work_order(wo)
    assert_documents_allowed(wo)
    receipt = ProductionReceipt.objects.create(
        company=wo.company, work_order=wo, doc_date=payload.get("doc_date"),
        is_final=bool(payload.get("is_final")), batch_no=(payload.get("batch_no") or "")[:64],
        exp_date=payload.get("exp_date"), mfg_date=payload.get("mfg_date"),
        notes=(payload.get("notes") or "")[:500], created_by=user, updated_by=user,
    )
    lines = payload.get("lines")
    if lines is None:
        remaining = max(ZERO, d(wo.qty) - produced_so_far(wo))
        lines = [{"kind": "MAIN", "qty_good": remaining}]
        scale = remaining / d(wo.qty) if d(wo.qty) else ZERO
        for out in wo.planned_outputs.all():
            lines.append({"kind": out.kind, "product": out.product, "qty_good": qty3(d(out.qty) * scale)})
    for ln in lines:
        kind = ln.get("kind") or "MAIN"
        product = wo.product if kind == "MAIN" else _resolve_fk(Product, wo.company, ln.get("product"))
        if product is None:
            raise rule("Each output line needs a product.", "MFG_LINE_NEEDS_COMPONENT")
        if kind == "MAIN" and ln.get("product") not in (None, "", wo.product_id, wo.product):
            raise rule("The main line is the product this work order makes.", "MFG_BAD_OUTPUT")
        PL.objects.create(
            receipt=receipt, company=wo.company, kind=kind, product=product,
            warehouse=_resolve_fk(Warehouse, wo.company, ln.get("warehouse")) or resolve_receipt_warehouse(
                wo, product, kind=kind,
            ),
            qty_good=qty3(ln.get("qty_good") or 0), qty_rejected=qty3(ln.get("qty_rejected") or 0),
            qty_rework=qty3(ln.get("qty_rework") or 0),
            reject_warehouse=_resolve_fk(Warehouse, wo.company, ln.get("reject_warehouse")),
            rework_warehouse=_resolve_fk(Warehouse, wo.company, ln.get("rework_warehouse")),
            serial_numbers=list(ln.get("serial_numbers") or []),
            recovery_rate=ln.get("recovery_rate"),
        )
    return receipt


# --- posting ---------------------------------------------------------------------------------

def _backflush(wo, receipt, produced, user, doc_date, can_backdate):
    """Issue the components marked 'take at completion' for the units this receipt produced."""
    rows = []
    for wl in wo.component_lines.select_related("component"):
        if wl.issue_method != "BACKFLUSH" or wl.principal_supplied or wl.alternate_of_id:
            continue
        need = qty3(d(wl.qty) * produced / d(wo.qty)) if d(wo.qty) else ZERO
        take = min(need, wl.qty_remaining)
        if take > 0:
            rows.append({"wo_line": wl, "qty": take})
    if not rows:
        return None
    issue = create_issue(wo, user, rows, doc_date=doc_date, notes=f"Taken at completion with {receipt.pk}")
    return post_issue(issue, user, can_backdate=can_backdate, is_manager=True, _backflush=True)


def _extra_costs(wo, produced) -> dict:
    """Flat extra cost (MFG-37) and conversion rates (MFG-28) for the units made now, by element.

    Only when the costing flag is on. Returns ``{element: amount}``.
    """
    out: dict[str, Decimal] = {}
    if wo.bom_id is None or not flag_enabled(wo.company, "MFG_COSTING_GL"):
        return out
    out_qty = d(wo.bom.output_qty) or Decimal("1")
    for ac in wo.bom.additional_costs.all():
        amt = d(ac.amount) * produced if ac.basis == "PER_UNIT" else d(ac.amount) * produced / out_qty
        out[ac.element] = out.get(ac.element, ZERO) + amt
    return {k: money(v) for k, v in out.items() if money(v) != 0}


def _additional_cost(wo, produced) -> Decimal:
    return sum(_extra_costs(wo, produced).values(), ZERO)


def standard_unit_cost(wo, on_date):
    """The standard cost in force for what this order makes, when standard costing is on."""
    if not flag_enabled(wo.company, "MFG_COSTING_GL") or wo.product_id is None:
        return None
    from manufacturing.models import StandardCost

    row = (
        StandardCost.objects.filter(company=wo.company, product_id=wo.product_id, effective_from__lte=on_date)
        .order_by("-effective_from").first()
    )
    return row.unit_cost if row is not None and row.unit_cost > 0 else None


@transaction.atomic
def post_receipt(receipt, user, *, can_backdate=True, is_manager=True, override_wip=False) -> ProductionReceipt:
    receipt = ProductionReceipt.objects.select_for_update().get(pk=receipt.pk)
    wo = lock_work_order(receipt.work_order_id)
    if receipt.status != DocumentStatus.DRAFT:
        raise rule("This receipt has already been posted.", "MFG_DOC_NOT_DRAFT")
    assert_documents_allowed(wo)
    doc_date = assert_doc_date(wo.company, receipt.doc_date, can_backdate=can_backdate, label="Receipt")
    cfg = get_settings(wo.company)
    lines = list(receipt.lines.select_related("product", "warehouse").order_by("id"))
    mains = [ln for ln in lines if ln.kind == PL.Kind.MAIN]
    if len(mains) != 1 or mains[0].product_id != wo.product_id:
        raise rule("A receipt has exactly one main line, for the product this work order makes.", "MFG_BAD_OUTPUT")
    main = mains[0]
    produced = d(main.qty_good) + d(main.qty_rework) + d(main.qty_rejected)
    if produced <= 0:
        raise rule("Enter how many units were made.", "MFG_BAD_QTY")
    cumulative = produced_so_far(wo) + produced
    ceiling = d(wo.qty) * (Decimal("1") + d(cfg.over_receipt_pct) / Decimal("100"))
    if cumulative > ceiling:
        raise rule(
            f"That would make {cumulative} against a plan of {wo.qty}. "
            f"Receipts can go {cfg.over_receipt_pct}% over the plan.",
            "MFG_OVER_RECEIPT",
        )
    is_final = bool(receipt.is_final) or cumulative >= d(wo.qty)
    for ln in lines:
        if ln.product.track_serial and (ln.qty_rejected or ln.qty_rework):
            raise rule(
                f"'{ln.product.name}' is tracked by serial number; rejected and rework units are not supported for it.",
                "MFG_SERIAL_REWORK_UNSUPPORTED",
            )

    if wo.principal_id:
        return _post_principal_receipt(receipt, wo, lines, main, produced, is_final, user, doc_date)

    # Material taken at completion goes out first, so the pool below includes it.
    backflush = _backflush(wo, receipt, produced, user, doc_date, can_backdate)
    wo = lock_work_order(wo.pk)
    extras = _extra_costs(wo, produced)
    absorbed = sum(extras.values(), ZERO)
    pool = d(wo.wip_value) + absorbed
    std = standard_unit_cost(wo, doc_date)

    planned = {(o.product_id, o.kind): o for o in wo.planned_outputs.all()}
    co_shares = sum((d(o.cost_share_pct) for o in wo.planned_outputs.all() if o.kind == "CO_PRODUCT"), ZERO)
    cost_lines, owners = [], []
    cost_lines.append({
        "kind": "MAIN", "qty": d(main.qty_good) + d(main.qty_rework), "est_unit": d(wo.estimated_unit_cost),
        "share": Decimal("100") - co_shares,
    })
    owners.append(("main", main))
    for ln in lines:
        if ln is main:
            continue
        out = planned.get((ln.product_id, ln.kind))
        if ln.kind == "CO_PRODUCT":
            cost_lines.append({
                "kind": "CO_PRODUCT", "qty": ln.qty_good,
                "est_unit": d(getattr(out, "estimated_unit_cost", 0)),
                "share": d(getattr(out, "cost_share_pct", None) if out else ln.cost_share_pct),
            })
        else:
            rate = ln.recovery_rate if ln.recovery_rate is not None else getattr(out, "recovery_rate", None)
            cost_lines.append({"kind": ln.kind, "qty": ln.qty_good, "recovery": d(rate or 0)})
        owners.append(("line", ln))
    if d(main.qty_rejected) > 0:
        cost_lines.append({"kind": "SCRAP", "qty": main.qty_rejected, "recovery": d(main.recovery_rate or 0)})
        owners.append(("rejected", main))

    if std is not None:
        # Standard costing: output is valued at standard on every receipt, the last included. What the
        # order actually cost beyond (or under) that stays in WIP and is cleared to variance at close.
        cost_lines[0]["est_unit"] = std
        amounts, residual, exceeds = cost_receipt(pool=pool, lines=cost_lines, is_final=False)
        exceeds = False
    else:
        amounts, residual, exceeds = cost_receipt(
            pool=pool, lines=cost_lines, is_final=is_final,
            tolerance_pct=cfg.final_receipt_tolerance_pct,
        )
    main_amount = amounts[0]
    if main_amount <= 0 and (d(main.qty_good) + d(main.qty_rework)) > 0:
        raise rule(
            "These materials have no cost on record, so the finished goods cannot be valued. "
            "Add the cost to the materials and try again.",
            "MFG_ZERO_COST_COMPLETE",
        )
    if exceeds and not (override_wip and is_manager):
        raise rule(
            "The cost of this receipt is more than the materials issued so far. "
            "Issue the materials first, or ask a manager to receive it anyway.",
            "MFG_RECEIPT_EXCEEDS_WIP",
        )

    gate_batch_no = receipt.batch_no
    stock_total = ZERO
    move_cache = {}
    for (kind, ln), amount in zip(owners, amounts):
        product = ln.product
        if kind == "main":
            good, rework = d(ln.qty_good), d(ln.qty_rework)
            units = good + rework
            unit_cost = unit4(amount / units) if units else ZERO
            line_cost, ids = ZERO, []
            if good > 0:
                batch = _output_batch(wo, product, gate_batch_no, receipt.exp_date, receipt.mfg_date, user, doc_date)
                ln.batch = batch
                if product.track_serial:
                    SerialNumberService.receive(
                        company=wo.company, product=product, warehouse=ln.warehouse,
                        numbers=ln.serial_numbers, quantity=good, user=user, allow_reactivate_scrap=True,
                    )
                mv = InventoryService.post_movement(
                    company=wo.company, product=product, warehouse=ln.warehouse, batch=batch,
                    movement_type=MovementType.MANUFACTURE_RECEIPT, quantity=good, unit_cost=unit_cost,
                    user=user, reference_type="mfg_receipt", reference_id=str(receipt.pk), movement_date=doc_date,
                )
                ids.append(mv.pk)
                line_cost += money(unit_cost * good)
                from quality import hooks as quality_hooks

                quality_hooks.hold_for_final_inspection(wo.company, product, batch, receipt.pk, good, user)
                trace.link_outputs(wo, product=product, batch=batch, serials=ln.serial_numbers if product.track_serial else None)
            if rework > 0:
                rw_wh = ln.rework_warehouse or cfg.quarantine_warehouse or ensure_aux_warehouse(wo.company, "QUARANTINE")
                mv = InventoryService.post_movement(
                    company=wo.company, product=product, warehouse=rw_wh, batch=_aux_batch(wo, product, "RW", user),
                    movement_type=MovementType.MANUFACTURE_RECEIPT, quantity=rework, unit_cost=unit_cost,
                    user=user, reference_type="mfg_rework", reference_id=str(receipt.pk), movement_date=doc_date,
                )
                ids.append(mv.pk)
                line_cost += money(unit_cost * rework)
            ln.unit_cost, ln.cost_amount, ln.movement_ids = unit_cost, line_cost, ids
            stock_total += line_cost
            move_cache[ln.pk] = line_cost
        elif kind == "rejected":
            qty = d(ln.qty_rejected)
            rate = d(ln.recovery_rate or 0)
            rj_wh = ln.reject_warehouse or cfg.scrap_warehouse or ensure_aux_warehouse(wo.company, "SCRAP")
            mv = InventoryService.post_movement(
                company=wo.company, product=product, warehouse=rj_wh, batch=_aux_batch(wo, product, "REJ", user),
                movement_type=MovementType.MANUFACTURE_RECEIPT, quantity=qty, unit_cost=rate,
                user=user, reference_type="mfg_receipt", reference_id=str(receipt.pk), movement_date=doc_date,
            )
            ln.movement_ids = list(ln.movement_ids or []) + [mv.pk]
            cost = money(rate * qty)
            ln.cost_amount = money(d(ln.cost_amount) + cost)
            stock_total += cost
        else:
            qty = d(ln.qty_good)
            if qty <= 0:
                ln.cost_amount, ln.movement_ids = ZERO, []
                continue
            unit_cost = unit4(amount / qty)
            batch = _output_batch(wo, product, gate_batch_no, receipt.exp_date, receipt.mfg_date, user, doc_date) \
                if ln.kind == "CO_PRODUCT" else _aux_batch(wo, product, "BP", user)
            ln.batch = batch
            mv = InventoryService.post_movement(
                company=wo.company, product=product, warehouse=ln.warehouse, batch=batch,
                movement_type=MovementType.MANUFACTURE_RECEIPT, quantity=qty, unit_cost=unit_cost,
                user=user, reference_type="mfg_receipt", reference_id=str(receipt.pk), movement_date=doc_date,
            )
            cost = money(unit_cost * qty)
            ln.unit_cost, ln.cost_amount, ln.movement_ids = unit_cost, cost, [mv.pk]
            stock_total += cost
        ln.save(update_fields=["batch", "unit_cost", "cost_amount", "movement_ids"])

    wo.qty_completed = d(wo.qty_completed) + d(main.qty_good)
    wo.qty_rework = d(wo.qty_rework) + d(main.qty_rework)
    wo.qty_rejected = d(wo.qty_rejected) + d(main.qty_rejected)
    wo.cost_received = money(d(wo.cost_received) + stock_total)
    wo.cost_absorbed = money(d(wo.cost_absorbed) + absorbed)
    if main.batch_id and not wo.batch_id:
        wo.batch = main.batch
        wo.batch_no = main.batch.batch_no
    if is_final:
        wo.status = WorkOrder.Status.COMPLETED
        wo.completed_at = doc_date
        reservation.release_all(wo)
    elif wo.status == WorkOrder.Status.RELEASED:
        wo.status = WorkOrder.Status.IN_PROGRESS
    wo.updated_by = user
    wo.save()
    receipt.status = DocumentStatus.POSTED
    receipt.number = next_number(wo.company, "mfg_receipt", "PR")
    receipt.doc_date = doc_date
    receipt.is_final = is_final
    receipt.total_cost = money(stock_total)
    receipt.absorbed_cost = absorbed
    receipt.backflush_issue = backflush
    receipt.posted_at = timezone.now()
    receipt.updated_by = user
    receipt.save()
    if posts_to_ledger(wo.company):
        from accounting.services import PostingService

        if absorbed > 0:
            PostingService.post_mfg_absorption(
                company=wo.company, source_type="MFG_ABSORB", source_id=receipt.pk, purpose="POST",
                entry_date=doc_date, credits=[(ABSORB_ACCOUNT[el], amt) for el, amt in extras.items()],
                narration=f"{receipt.number} extra cost on {wo.number or wo.pk}", user=user,
            )
        PostingService.post_mfg_wip(
            company=wo.company, source_type="MFG_RECEIPT", source_id=receipt.pk, purpose="POST",
            entry_date=doc_date, amount=stock_total, into_wip=False,
            narration=f"{receipt.number} output of {wo.number or wo.pk}", user=user,
        )
    AuditService.log(
        action="mfg.receipt.posted", company=wo.company, user=user, entity_type="ProductionReceipt",
        entity_id=str(receipt.pk), description=f"{receipt.number} for {wo.number or wo.pk}: {stock_total}",
    )
    return receipt


def _post_principal_receipt(receipt, wo, lines, main, produced, is_final, user, doc_date):
    """Output of a customer's job work: goods ready to go back to them. Not our stock, not our books."""
    from jobwork.services import principal as principal_book

    if len(lines) != 1:
        raise rule(
            "A job work order for a customer makes only the processed goods. Record scrap on the job work order.",
            "MFG_BAD_OUTPUT",
        )
    good = d(main.qty_good)
    if good > 0:
        principal_book.produce(
            wo.company, user, principal=wo.principal, product=wo.product, qty=good, when=doc_date,
            work_order_id=wo.pk, reference=f"receipt:{receipt.pk}",
        )
    main.unit_cost, main.cost_amount, main.movement_ids = ZERO, ZERO, []
    main.save(update_fields=["unit_cost", "cost_amount", "movement_ids"])
    wo.qty_completed = d(wo.qty_completed) + good
    wo.qty_rework = d(wo.qty_rework) + d(main.qty_rework)
    wo.qty_rejected = d(wo.qty_rejected) + d(main.qty_rejected)
    if is_final:
        wo.status = WorkOrder.Status.COMPLETED
        wo.completed_at = doc_date
        reservation.release_all(wo)
    elif wo.status == WorkOrder.Status.RELEASED:
        wo.status = WorkOrder.Status.IN_PROGRESS
    wo.updated_by = user
    wo.save()
    receipt.status = DocumentStatus.POSTED
    receipt.number = next_number(wo.company, "mfg_receipt", "PR")
    receipt.doc_date = doc_date
    receipt.is_final = is_final
    receipt.total_cost = ZERO
    receipt.absorbed_cost = ZERO
    receipt.posted_at = timezone.now()
    receipt.updated_by = user
    receipt.save()
    AuditService.log(
        action="mfg.receipt.posted", company=wo.company, user=user, entity_type="ProductionReceipt",
        entity_id=str(receipt.pk), description=f"{receipt.number} for {wo.number or wo.pk}: {good} for {wo.principal.name}",
    )
    return receipt


# --- reversal --------------------------------------------------------------------------------

@transaction.atomic
def reverse_receipt(receipt, user, reason, *, can_backdate=True) -> ProductionReceipt:
    receipt = ProductionReceipt.objects.select_for_update().get(pk=receipt.pk)
    wo = lock_work_order(receipt.work_order_id)
    if receipt.status != DocumentStatus.POSTED:
        raise rule("Only a posted receipt can be reversed.", "MFG_DOC_NOT_POSTED")
    if not (reason or "").strip():
        raise rule("Say why this receipt is being reversed.", "MFG_REASON_REQUIRED")
    if wo.status == WorkOrder.Status.CLOSED:
        raise rule("Reopen the closed work order before reversing documents on it.", "MFG_REVERSAL_ORDER")
    later = ProductionReceipt.objects.filter(
        work_order=wo, status=DocumentStatus.POSTED, pk__gt=receipt.pk,
    ).first()
    if later is not None:
        raise rule(
            f"{later.number} was posted after this receipt. Reverse it first.", "MFG_REVERSAL_ORDER",
        )
    doc_date = assert_doc_date(wo.company, receipt.doc_date, allow_soft_closed=True, label="Reversal")
    if wo.principal_id:
        from jobwork.services import principal as principal_book

        if principal_book.on_hand(wo.company, wo.principal, wo.product) < sum(
            (d(ln.qty_good) for ln in receipt.lines.all()), ZERO
        ):
            raise rule("Those goods have already gone back to the customer.", "MFG_REVERSAL_ORDER")
        principal_book.reverse_reference(wo.company, wo.pk, f"receipt:{receipt.pk}")
        for ln in receipt.lines.all():
            wo.qty_completed = d(wo.qty_completed) - d(ln.qty_good)
            wo.qty_rework = d(wo.qty_rework) - d(ln.qty_rework)
            wo.qty_rejected = d(wo.qty_rejected) - d(ln.qty_rejected)
        if wo.status == WorkOrder.Status.COMPLETED:
            wo.status = WorkOrder.Status.IN_PROGRESS
            wo.completed_at = None
        wo.save()
        receipt.status = DocumentStatus.REVERSED
        receipt.reversed_at = timezone.now()
        receipt.reversed_by = user
        receipt.reverse_reason = reason[:500]
        receipt.save(update_fields=["status", "reversed_at", "reversed_by", "reverse_reason", "updated_at"])
        return receipt
    lines = list(receipt.lines.select_related("product", "warehouse"))
    # Output that has been sold or used cannot be taken back out.
    for ln in lines:
        for mid in ln.movement_ids or []:
            mv = StockMovement.objects.select_related("product", "warehouse", "batch").get(pk=mid)
            if InventoryService.available_quantity(wo.company, mv.product, mv.warehouse, mv.batch) < mv.quantity:
                raise rule(
                    f"'{mv.product.name}' from this receipt has already been sold or used.",
                    "MFG_REVERSAL_ORDER",
                )
    stock_total = ZERO
    for ln in lines:
        for mid in ln.movement_ids or []:
            mv = StockMovement.objects.select_related("product", "warehouse", "batch").get(pk=mid)
            InventoryService.post_movement(
                company=wo.company, product=mv.product, warehouse=mv.warehouse, batch=mv.batch,
                movement_type=MovementType.MANUFACTURE_REVERSAL, quantity=-abs(mv.quantity),
                unit_cost=mv.unit_cost, user=user, reference_type="mfg_receipt_reverse",
                reference_id=str(receipt.pk), movement_date=doc_date, reason=reason[:255],
            )
            InventoryService.retire_source_layers(mv, abs(d(mv.quantity)))
        if ln.product.track_serial and ln.serial_numbers and ln.kind == PL.Kind.MAIN:
            SerialNumberService.transition(
                company=wo.company, product=ln.product, warehouse=ln.warehouse,
                numbers=[str(s).strip() for s in ln.serial_numbers if str(s).strip()],
                quantity=ln.qty_good, source=SerialNumber.Status.AVAILABLE,
                target=SerialNumber.Status.SCRAPPED, user=user,
            )
        stock_total += d(ln.cost_amount)
        if ln.kind == PL.Kind.MAIN:
            wo.qty_completed = d(wo.qty_completed) - d(ln.qty_good)
            wo.qty_rework = d(wo.qty_rework) - d(ln.qty_rework)
            wo.qty_rejected = d(wo.qty_rejected) - d(ln.qty_rejected)
    wo.cost_received = money(d(wo.cost_received) - stock_total)
    wo.cost_absorbed = money(d(wo.cost_absorbed) - d(receipt.absorbed_cost))
    wo.updated_by = user
    wo.save(update_fields=[
        "qty_completed", "qty_rework", "qty_rejected", "cost_received", "cost_absorbed",
        "updated_at", "updated_by",
    ])
    if posts_to_ledger(wo.company):
        from accounting.services import PostingService

        PostingService.reverse_mfg_document(
            company=wo.company, source_type="MFG_RECEIPT", source_id=receipt.pk, user=user, entry_date=doc_date,
        )
        PostingService.reverse_mfg_document(
            company=wo.company, source_type="MFG_ABSORB", source_id=receipt.pk, user=user, entry_date=doc_date,
        )
    from quality import hooks as quality_hooks

    quality_hooks.cancel_for_receipt(wo.company, receipt.pk, user)
    # Open the order again, hold its materials again, and take back the materials that were
    # issued at completion, now that no output carries their cost.
    wo = lock_work_order(wo.pk)
    if wo.status == WorkOrder.Status.COMPLETED:
        wo.status = WorkOrder.Status.IN_PROGRESS
        wo.completed_at = None
        wo.save(update_fields=["status", "completed_at", "updated_at"])
    receipt.status = DocumentStatus.REVERSED
    receipt.reversed_at = timezone.now()
    receipt.reversed_by = user
    receipt.reverse_reason = reason[:500]
    receipt.save(update_fields=["status", "reversed_at", "reversed_by", "reverse_reason", "updated_at"])
    if receipt.backflush_issue_id:
        reverse_issue(MaterialIssue.objects.get(pk=receipt.backflush_issue_id), user, f"With {receipt.number}: {reason}"[:500])
    wo = lock_work_order(wo.pk)
    if wo.status == WorkOrder.Status.IN_PROGRESS and not _has_other_posted_documents(wo):
        wo.status = WorkOrder.Status.RELEASED
        wo.save(update_fields=["status", "updated_at"])
    AuditService.log(
        action="mfg.receipt.reversed", company=wo.company, user=user, entity_type="ProductionReceipt",
        entity_id=str(receipt.pk), description=f"{receipt.number}: {reason[:200]}",
    )
    return receipt
