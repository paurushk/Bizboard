"""Material issue and material return documents (MFG-06, MFG-07)."""

from accounting.books import posts_to_ledger
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from core.services.audit import AuditService
from inventory.models import BatchLot, MovementType, SerialNumber, StockMovement, Warehouse
from inventory.services import InventoryService, InventoryValuationService, SerialNumberService
from masters.models import Product

from manufacturing.models import (
    DocumentStatus, MaterialIssue, MaterialIssueLine, MaterialReturn, MaterialReturnLine,
    WorkOrder, WorkOrderLine,
)

from . import reservation, trace
from .allocation import allocate_batches
from .common import (
    ZERO, assert_doc_date, d, get_settings, money, next_number, qty3, resolve_issue_warehouse, rule,
    unit4,
)

POSTING_STATUSES = (WorkOrder.Status.RELEASED, WorkOrder.Status.IN_PROGRESS)


def _pk(value):
    return getattr(value, "pk", value)


def lock_work_order(wo) -> WorkOrder:
    return WorkOrder.objects.select_for_update().get(pk=_pk(wo))


def assert_documents_allowed(wo, *, statuses=POSTING_STATUSES):
    if wo.issue_mode != WorkOrder.IssueMode.SEPARATE:
        raise rule(
            "This work order issues all its materials when it is released. "
            "Switch the company to separate issue documents to use them.",
            "MFG_LEGACY_MODE",
        )
    if wo.status not in statuses:
        raise rule(
            f"A work order that is {wo.status.lower().replace('_', ' ')} cannot take this document.",
            "MFG_BAD_WO_STATUS",
        )


# --- drafts ----------------------------------------------------------------------------------

def _resolve_wo_line(wo, payload):
    wo_line = payload.get("wo_line")
    if wo_line is not None:
        found = WorkOrderLine.objects.filter(pk=_pk(wo_line), work_order=wo).first()
        if found is None:
            raise rule("That material line does not belong to this work order.", "MFG_BAD_WO_LINE")
        return found
    component = payload.get("component")
    if component is not None:
        return wo.component_lines.filter(component_id=_pk(component)).order_by("id").first()
    return None


def _resolve_fk(model, company, value):
    if value is None or value == "":
        return None
    if isinstance(value, model):
        if value.company_id != company.id:
            raise rule(f"{model.__name__} does not belong to this company.", "MFG_BAD_REFERENCE")
        return value
    found = model.objects.filter(pk=value, company=company).first()
    if found is None:
        raise rule(f"{model.__name__} {value} does not belong to this company.", "MFG_BAD_REFERENCE")
    return found


@transaction.atomic
def create_issue(wo, user, lines=None, *, doc_date=None, notes="") -> MaterialIssue:
    """A draft issue. With no ``lines`` it asks for everything the work order still needs.

    Backflush lines are left out of the default: they are taken when output is received.
    """
    wo = lock_work_order(wo)
    assert_documents_allowed(wo)
    issue = MaterialIssue.objects.create(
        company=wo.company, work_order=wo, doc_date=doc_date, notes=notes,
        created_by=user, updated_by=user,
    )
    if lines is None:
        lines = [
            {"wo_line": ln, "qty": ln.qty_remaining}
            for ln in wo.component_lines.select_related("component")
            if ln.qty_remaining > 0 and ln.issue_method != "BACKFLUSH" and ln.alternate_of_id is None
        ]
    if not lines:
        raise rule("There is nothing left to issue for this work order.", "MFG_NOTHING_TO_ISSUE")
    for payload in lines:
        wo_line = _resolve_wo_line(wo, payload)
        component = _resolve_fk(Product, wo.company, payload.get("component")) if payload.get("component") else None
        component = component or (wo_line.component if wo_line else None)
        if component is None:
            raise rule("Each line needs a material.", "MFG_LINE_NEEDS_COMPONENT")
        _assert_substitute_allowed(wo_line, component)
        qty = qty3(payload.get("qty"))
        if qty <= 0:
            raise rule("Quantity must be greater than zero.", "MFG_BAD_QTY")
        MaterialIssueLine.objects.create(
            issue=issue, company=wo.company, wo_line=wo_line, component=component, qty=qty,
            warehouse=_resolve_fk(Warehouse, wo.company, payload.get("warehouse"))
            or resolve_issue_warehouse(wo, component, line=wo_line),
            batch=_resolve_fk(BatchLot, wo.company, payload.get("batch")),
            serial_numbers=list(payload.get("serial_numbers") or []),
            lot_allocations=list(payload.get("lot_allocations") or []),
            extra_reason=(payload.get("extra_reason") or "")[:255],
        )
    return issue


# --- posting ---------------------------------------------------------------------------------

def _assert_substitute_allowed(wo_line, component):
    """Issuing a different material against a line is allowed only for its listed alternates."""
    if wo_line is None or component.pk == wo_line.component_id:
        return
    if not wo_line.alternates.filter(component=component).exists():
        raise rule(
            f"'{component.name}' is not an alternate for '{wo_line.component.name}' on this recipe.",
            "MFG_NOT_AN_ALTERNATE",
        )


def _is_extra(wo_line, qty) -> bool:
    return wo_line is None or qty > wo_line.qty_remaining


def _over_issue_pct(wo_line, qty) -> Decimal:
    if wo_line is None or wo_line.qty <= 0:
        return Decimal("100")
    over = d(qty) - wo_line.qty_remaining
    return max(ZERO, over) * Decimal("100") / d(wo_line.qty)


def _over_limit(lines, cfg, wo) -> list[str]:
    """Names of the materials in this draft that go further over the plan than a floor user may post."""
    wanted: dict[int, Decimal] = {}
    names: list[str] = []
    for ln in lines:
        wl = ln.wo_line
        total = wanted.get(wl.pk if wl else 0, ZERO) + ln.qty
        wanted[wl.pk if wl else 0] = total
        extra = _is_extra(wl, ln.qty) if wl is None else total > wl.qty_remaining
        if extra:
            over_pct = _over_issue_pct(wl, total) if wl is not None else Decimal("100")
            if over_pct > d(cfg.extra_issue_approval_pct):
                names.append(ln.component.name)
    return names


@transaction.atomic
def request_approval(issue, user, note="") -> MaterialIssue:
    """A floor user asks a manager to approve (and post) a draft that goes over the plan."""
    issue = MaterialIssue.objects.select_for_update().get(pk=issue.pk)
    wo = lock_work_order(issue.work_order_id)
    if issue.status != DocumentStatus.DRAFT:
        raise rule("Only a draft can be sent for approval.", "MFG_DOC_NOT_DRAFT")
    if issue.approval == MaterialIssue.Approval.REQUESTED:
        raise rule("A manager has already been asked about this issue.", "MFG_APPROVAL_PENDING")
    lines = list(issue.lines.select_related("component", "wo_line"))
    if not _over_limit(lines, get_settings(wo.company), wo):
        raise rule("This issue is within the plan, so no approval is needed. Post it.", "MFG_APPROVAL_NOT_NEEDED")
    for ln in lines:
        if not (ln.extra_reason or "").strip() and (ln.wo_line_id is None or ln.qty > ln.wo_line.qty_remaining):
            raise rule(f"Say why '{ln.component.name}' is more than the order needs.", "MFG_EXTRA_NEEDS_REASON")
    issue.approval = MaterialIssue.Approval.REQUESTED
    issue.approval_note = (note or "")[:500]
    issue.approval_requested_by = user
    issue.approval_decided_by = None
    issue.approval_decided_at = None
    issue.save(update_fields=[
        "approval", "approval_note", "approval_requested_by", "approval_decided_by", "approval_decided_at", "updated_at",
    ])
    AuditService.log(
        action="mfg.issue.approval_requested", company=wo.company, user=user, entity_type="MaterialIssue",
        entity_id=str(issue.pk), description=f"{wo.number}: approval asked for extra material",
    )
    return issue


@transaction.atomic
def decide_approval(issue, user, *, approve: bool, note="", can_backdate=True) -> MaterialIssue:
    """A manager approves (which posts the issue) or turns the request down."""
    issue = MaterialIssue.objects.select_for_update().get(pk=issue.pk)
    wo = lock_work_order(issue.work_order_id)
    if issue.status != DocumentStatus.DRAFT or issue.approval != MaterialIssue.Approval.REQUESTED:
        raise rule("There is no open request on this issue.", "MFG_APPROVAL_NONE")
    if not approve and not (note or "").strip():
        raise rule("Say why the request is turned down.", "MFG_REASON_REQUIRED")
    issue.approval = MaterialIssue.Approval.APPROVED if approve else MaterialIssue.Approval.REJECTED
    issue.approval_decided_by = user
    issue.approval_decided_at = timezone.now()
    if note:
        issue.approval_note = (note or "")[:500]
    issue.save(update_fields=["approval", "approval_decided_by", "approval_decided_at", "approval_note", "updated_at"])
    AuditService.log(
        action="mfg.issue.approved" if approve else "mfg.issue.rejected", company=wo.company, user=user,
        entity_type="MaterialIssue", entity_id=str(issue.pk),
        description=f"{wo.number}: extra material {'approved' if approve else 'turned down'}",
    )
    if approve:
        return post_issue(issue, user, can_backdate=can_backdate, is_manager=True)
    return issue


@transaction.atomic
def post_issue(issue, user, *, can_backdate=True, is_manager=True, _backflush=False) -> MaterialIssue:
    """Take the materials out of stock into the work order's WIP."""
    issue = MaterialIssue.objects.select_for_update().get(pk=issue.pk)
    wo = lock_work_order(issue.work_order_id)
    if issue.status != DocumentStatus.DRAFT:
        raise rule("This issue has already been posted.", "MFG_DOC_NOT_DRAFT")
    assert_documents_allowed(wo)
    doc_date = assert_doc_date(wo.company, issue.doc_date, can_backdate=can_backdate, label="Issue")
    cfg = get_settings(wo.company)
    lines = list(issue.lines.select_related("component", "wo_line", "warehouse", "batch").order_by("id"))
    if not lines:
        raise rule("An issue needs at least one line.", "MFG_EMPTY_DOC")

    # Rules first, stock second: nothing is posted until every line has passed.
    wanted_by_wo_line: dict[int, Decimal] = {}
    for ln in lines:
        wl = ln.wo_line
        if wl is not None and wl.principal_supplied and wo.principal_id is None:
            raise rule("Name the customer whose material this is on the work order.", "MFG_PRINCIPAL_MATERIAL")
        total = wanted_by_wo_line.get(wl.pk if wl else 0, ZERO) + ln.qty
        wanted_by_wo_line[wl.pk if wl else 0] = total
        extra = _is_extra(wl, ln.qty) if wl is None else total > wl.qty_remaining
        ln.is_extra = bool(extra)
        if extra:
            if not ln.extra_reason.strip():
                raise rule(
                    f"'{ln.component.name}' is more than this work order still needs. Say why.",
                    "MFG_EXTRA_NEEDS_REASON",
                )
            over_pct = _over_issue_pct(wl, total) if wl is not None else Decimal("100")
            if over_pct > d(cfg.extra_issue_approval_pct) and not is_manager:
                raise rule(
                    f"'{ln.component.name}' goes {over_pct.quantize(Decimal('0.1'))}% over what the work "
                    f"order needs. A manager must post this issue.",
                    "MFG_EXTRA_NEEDS_MANAGER",
                )

    total_cost = ZERO
    for ln in lines:
        comp = ln.component
        warehouse = ln.warehouse
        if ln.wo_line_id and ln.wo_line.principal_supplied:
            # The customer's material: out of their book, never out of our stock or our ledger.
            from jobwork.services import principal as principal_book

            principal_book.consume(
                wo.company, user, principal=wo.principal, product=comp, qty=ln.qty, when=doc_date,
                work_order_id=wo.pk, reference=f"issue:{issue.pk}",
            )
            ln.unit_cost, ln.cost_amount, ln.movement_ids = ZERO, ZERO, []
            ln.save(update_fields=["is_extra", "unit_cost", "cost_amount", "movement_ids"])
            WorkOrderLine.objects.filter(pk=ln.wo_line_id).update(qty_issued=F("qty_issued") + ln.qty)
            ln.wo_line.qty_issued = ln.wo_line.qty_issued + ln.qty
            continue
        # Lift this order's own hold so it does not block its own material.
        reservation.release_for_issue(wo, ln.wo_line.component if ln.wo_line_id else comp, ln.qty)
        plan = allocate_batches(
            wo.company, warehouse, comp, ln.qty,
            batch=ln.batch, lot_allocations=ln.lot_allocations,
        )
        move_ids, line_cost = [], ZERO
        lot_payload = []
        for batch, take in plan:
            cost_hint = InventoryValuationService.unit_cost(wo.company, comp, warehouse, batch=batch)
            move = InventoryService.post_movement(
                company=wo.company, product=comp, warehouse=warehouse, batch=batch,
                movement_type=MovementType.MANUFACTURE_ISSUE, quantity=take, unit_cost=cost_hint,
                user=user, reference_type="mfg_backflush" if _backflush else "mfg_issue",
                reference_id=str(issue.pk), movement_date=doc_date,
            )
            move_ids.append(move.pk)
            line_cost += d(move.unit_cost) * take
            if batch is not None:
                lot_payload.append({"batch_id": batch.pk, "batch_no": batch.batch_no, "qty": str(take)})
        serials = [str(s).strip() for s in (ln.serial_numbers or []) if str(s).strip()]
        if comp.track_serial:
            if not serials:
                raise rule(f"Serial numbers are required to issue '{comp.name}'.", "MFG_SERIALS_REQUIRED")
            SerialNumberService.transition(
                company=wo.company, product=comp, warehouse=warehouse, numbers=serials,
                quantity=ln.qty, source=SerialNumber.Status.AVAILABLE,
                target=SerialNumber.Status.CONSUMED, user=user,
            )
            trace.record_inputs(
                wo, document_type="issue", document_id=issue.pk, component=comp,
                serials=serials, qty=ln.qty,
            )
        else:
            for batch, take in plan:
                trace.record_inputs(
                    wo, document_type="issue", document_id=issue.pk, component=comp, batch=batch, qty=take,
                )
        ln.lot_allocations = lot_payload or ln.lot_allocations
        ln.movement_ids = move_ids
        ln.cost_amount = money(line_cost)
        ln.unit_cost = unit4(line_cost / ln.qty) if ln.qty else ZERO
        ln.save(update_fields=[
            "is_extra", "lot_allocations", "movement_ids", "cost_amount", "unit_cost", "serial_numbers",
        ])
        total_cost += ln.cost_amount
        if ln.wo_line_id:
            WorkOrderLine.objects.filter(pk=ln.wo_line_id).update(qty_issued=F("qty_issued") + ln.qty)
            ln.wo_line.qty_issued = ln.wo_line.qty_issued + ln.qty

    wo.cost_issued = money(d(wo.cost_issued) + total_cost)
    if wo.status == WorkOrder.Status.RELEASED:
        wo.status = WorkOrder.Status.IN_PROGRESS
    wo.updated_by = user
    wo.save(update_fields=["cost_issued", "status", "updated_at", "updated_by"])
    issue.status = DocumentStatus.POSTED
    issue.number = next_number(wo.company, "mfg_issue", "MI")
    issue.doc_date = doc_date
    issue.posted_at = timezone.now()
    issue.updated_by = user
    fields = ["status", "number", "doc_date", "posted_at", "updated_by", "updated_at"]
    if issue.approval == MaterialIssue.Approval.REQUESTED and is_manager:
        # A manager posting the draft is the approval; the request must not be left looking open.
        issue.approval, issue.approval_decided_by, issue.approval_decided_at = (
            MaterialIssue.Approval.APPROVED, user, timezone.now(),
        )
        fields += ["approval", "approval_decided_by", "approval_decided_at"]
    issue.save(update_fields=fields)
    if posts_to_ledger(wo.company):
        from accounting.services import PostingService

        PostingService.post_mfg_wip(
            company=wo.company, source_type="MFG_ISSUE", source_id=issue.pk, purpose="POST",
            entry_date=doc_date, amount=total_cost, into_wip=True,
            narration=f"{issue.number} materials to {wo.number or wo.pk}", user=user,
        )
    AuditService.log(
        action="mfg.issue.posted", company=wo.company, user=user, entity_type="MaterialIssue",
        entity_id=str(issue.pk), description=f"{issue.number} for {wo.number or wo.pk}: {total_cost}",
    )
    return issue


# --- reversal --------------------------------------------------------------------------------

def _issue_net_cost(issue) -> Decimal:
    gross = sum((ln.cost_amount for ln in issue.lines.all()), ZERO)
    returned = sum(
        (rl.cost_amount for rl in MaterialReturnLine.objects.filter(
            source_issue_line__issue=issue, material_return__status=DocumentStatus.POSTED,
        )),
        ZERO,
    )
    return d(gross) - d(returned)


@transaction.atomic
def reverse_issue(issue, user, reason, *, can_backdate=True) -> MaterialIssue:
    issue = MaterialIssue.objects.select_for_update().get(pk=issue.pk)
    wo = lock_work_order(issue.work_order_id)
    if issue.status != DocumentStatus.POSTED:
        raise rule("Only a posted issue can be reversed.", "MFG_DOC_NOT_POSTED")
    if not (reason or "").strip():
        raise rule("Say why this issue is being reversed.", "MFG_REASON_REQUIRED")
    if wo.status == WorkOrder.Status.CLOSED:
        raise rule("Reopen the closed work order before reversing documents on it.", "MFG_REVERSAL_ORDER")
    if MaterialReturnLine.objects.filter(
        source_issue_line__issue=issue, material_return__status=DocumentStatus.POSTED,
    ).exists():
        raise rule(
            "Materials from this issue have been returned. Reverse the return first.", "MFG_REVERSAL_ORDER",
        )
    net = _issue_net_cost(issue)
    if d(wo.wip_value) - net < Decimal("-0.005"):
        raise rule(
            "Finished goods have already taken the cost of these materials. "
            "Reverse the production receipts first.",
            "MFG_REVERSAL_ORDER",
        )
    doc_date = assert_doc_date(
        wo.company, issue.doc_date, allow_soft_closed=True, can_backdate=True, label="Reversal",
    )
    if wo.principal_id:
        from jobwork.services import principal as principal_book

        principal_book.reverse_reference(wo.company, wo.pk, f"issue:{issue.pk}")
    for ln in issue.lines.select_related("component", "wo_line", "warehouse").order_by("id"):
        for mid in ln.movement_ids or []:
            move = StockMovement.objects.select_related("product", "warehouse", "batch").get(pk=mid)
            inbound = InventoryService.post_movement(
                company=wo.company, product=move.product, warehouse=move.warehouse, batch=move.batch,
                movement_type=MovementType.MANUFACTURE_REVERSAL, quantity=abs(move.quantity),
                unit_cost=move.unit_cost, user=user, reference_type="mfg_issue_reverse",
                reference_id=str(issue.pk), movement_date=doc_date, reason=reason[:255],
            )
            InventoryService.restore_fifo_peels(move, inbound)
        if ln.component.track_serial and ln.serial_numbers:
            SerialNumberService.transition(
                company=wo.company, product=ln.component, warehouse=ln.warehouse,
                numbers=[str(s).strip() for s in ln.serial_numbers if str(s).strip()],
                quantity=ln.qty, source=SerialNumber.Status.CONSUMED,
                target=SerialNumber.Status.AVAILABLE, user=user,
            )
        if ln.wo_line_id:
            WorkOrderLine.objects.filter(pk=ln.wo_line_id).update(qty_issued=F("qty_issued") - ln.qty)
            ln.wo_line.qty_issued = ln.wo_line.qty_issued - ln.qty
            # The material is needed again: hold it.
            reservation.reserve_line(wo, WorkOrderLine.objects.select_related("component").get(pk=ln.wo_line_id), user, qty=ln.qty)
    gross = sum((ln.cost_amount for ln in issue.lines.all()), ZERO)
    wo.cost_issued = money(d(wo.cost_issued) - gross)
    wo.updated_by = user
    if wo.status == WorkOrder.Status.IN_PROGRESS and not _has_other_posted_documents(wo, issue):
        wo.status = WorkOrder.Status.RELEASED
    wo.save(update_fields=["cost_issued", "status", "updated_at", "updated_by"])
    if posts_to_ledger(wo.company):
        from accounting.services import PostingService

        PostingService.reverse_mfg_document(
            company=wo.company, source_type="MFG_ISSUE", source_id=issue.pk, user=user, entry_date=doc_date,
        )
    trace.reverse_document(wo, document_type="issue", document_id=issue.pk)
    issue.status = DocumentStatus.REVERSED
    issue.reversed_at = timezone.now()
    issue.reversed_by = user
    issue.reverse_reason = reason[:500]
    issue.save(update_fields=["status", "reversed_at", "reversed_by", "reverse_reason", "updated_at"])
    AuditService.log(
        action="mfg.issue.reversed", company=wo.company, user=user, entity_type="MaterialIssue",
        entity_id=str(issue.pk), description=f"{issue.number}: {reason[:200]}",
    )
    return issue


def _has_other_posted_documents(wo, current=None) -> bool:
    from manufacturing.models import ProductionReceipt

    issues = MaterialIssue.objects.filter(work_order=wo, status=DocumentStatus.POSTED)
    if current is not None and isinstance(current, MaterialIssue):
        issues = issues.exclude(pk=current.pk)
    returns = MaterialReturn.objects.filter(work_order=wo, status=DocumentStatus.POSTED)
    if current is not None and isinstance(current, MaterialReturn):
        returns = returns.exclude(pk=current.pk)
    receipts = ProductionReceipt.objects.filter(work_order=wo, status=DocumentStatus.POSTED)
    if current is not None and isinstance(current, ProductionReceipt):
        receipts = receipts.exclude(pk=current.pk)
    return issues.exists() or returns.exists() or receipts.exists()


# --- returns ---------------------------------------------------------------------------------

@transaction.atomic
def create_return(wo, user, lines, *, doc_date=None, notes="") -> MaterialReturn:
    wo = lock_work_order(wo)
    assert_documents_allowed(wo, statuses=POSTING_STATUSES + (WorkOrder.Status.COMPLETED,))
    if not lines:
        raise rule("A return needs at least one line.", "MFG_EMPTY_DOC")
    ret = MaterialReturn.objects.create(
        company=wo.company, work_order=wo, doc_date=doc_date, notes=notes, created_by=user, updated_by=user,
    )
    for payload in lines:
        wo_line = _resolve_wo_line(wo, payload)
        if wo_line is None:
            raise rule("A return must name the material line it comes from.", "MFG_LINE_NEEDS_COMPONENT")
        back_component = (
            _resolve_fk(Product, wo.company, payload.get("component")) if payload.get("component") else wo_line.component
        )
        _assert_substitute_allowed(wo_line, back_component)
        qty = qty3(payload.get("qty"))
        if qty <= 0:
            raise rule("Quantity must be greater than zero.", "MFG_BAD_QTY")
        source = payload.get("source_issue_line")
        source = MaterialIssueLine.objects.filter(pk=_pk(source), issue__work_order=wo).first() if source else None
        warehouse = _resolve_fk(Warehouse, wo.company, payload.get("warehouse")) or (
            source.warehouse if source else resolve_issue_warehouse(wo, wo_line.component, line=wo_line)
        )
        MaterialReturnLine.objects.create(
            material_return=ret, company=wo.company, wo_line=wo_line, component=back_component, qty=qty,
            warehouse=warehouse, batch=_resolve_fk(BatchLot, wo.company, payload.get("batch")),
            serial_numbers=list(payload.get("serial_numbers") or []), source_issue_line=source,
        )
    return ret


def _issued_movements(wo, component, warehouse, batch):
    """Posted issue movements of this order for a component, newest first, with what is already back."""
    lines = MaterialIssueLine.objects.filter(
        issue__work_order=wo, issue__status=DocumentStatus.POSTED, component=component, warehouse=warehouse,
    )
    ids = [mid for ln in lines for mid in (ln.movement_ids or [])]
    moves = StockMovement.objects.filter(pk__in=ids, product=component, warehouse=warehouse)
    if batch is not None:
        moves = moves.filter(batch=batch)
    back: dict[int, Decimal] = {}
    for rl in MaterialReturnLine.objects.filter(
        material_return__work_order=wo, material_return__status=DocumentStatus.POSTED, component=component,
    ):
        for src in rl.sources or []:
            back[int(src["move"])] = back.get(int(src["move"]), ZERO) + d(src["qty"])
    out = []
    for mv in moves.order_by("-id"):
        free = abs(d(mv.quantity)) - back.get(mv.pk, ZERO)
        if free > 0:
            out.append((mv, free))
    return out


@transaction.atomic
def post_return(ret, user, *, can_backdate=True) -> MaterialReturn:
    ret = MaterialReturn.objects.select_for_update().get(pk=ret.pk)
    wo = lock_work_order(ret.work_order_id)
    if ret.status != DocumentStatus.DRAFT:
        raise rule("This return has already been posted.", "MFG_DOC_NOT_DRAFT")
    assert_documents_allowed(wo, statuses=POSTING_STATUSES + (WorkOrder.Status.COMPLETED,))
    doc_date = assert_doc_date(wo.company, ret.doc_date, can_backdate=can_backdate, label="Return")
    lines = list(ret.lines.select_related("component", "wo_line", "warehouse", "batch").order_by("id"))
    if not lines:
        raise rule("A return needs at least one line.", "MFG_EMPTY_DOC")
    total = ZERO
    for ln in lines:
        wl = ln.wo_line
        issued_net = d(wl.qty_issued) - d(wl.qty_returned)
        if ln.qty > issued_net:
            raise rule(
                f"Only {issued_net} of '{ln.component.name}' is out on this work order; "
                f"{ln.qty} cannot come back.",
                "MFG_OVER_RETURN",
            )
        available = _issued_movements(wo, ln.component, ln.warehouse, ln.batch)
        if sum((free for _m, free in available), ZERO) < ln.qty:
            raise rule(
                f"'{ln.component.name}' was not issued from that godown and batch in this quantity.",
                "MFG_OVER_RETURN",
            )
        remaining, sources, cost_total, move_ids = ln.qty, [], ZERO, []
        # Newest issue first: those are the layers most recently peeled.
        for mv, free in available:
            if remaining <= 0:
                break
            take = min(remaining, free)
            inbound = InventoryService.post_movement(
                company=wo.company, product=ln.component, warehouse=ln.warehouse, batch=mv.batch,
                movement_type=MovementType.MANUFACTURE_RETURN, quantity=take, unit_cost=mv.unit_cost,
                user=user, reference_type="mfg_return", reference_id=str(ret.pk), movement_date=doc_date,
            )
            posted_ids = [
                str(i) for i in MaterialReturn.objects.filter(
                    work_order=wo, status=DocumentStatus.POSTED,
                ).values_list("pk", flat=True)
            ] + [str(ret.pk)]
            already = InventoryService.already_restored_by_layer(
                mv, StockMovement.objects.filter(
                    company=wo.company, reference_type="mfg_return", reference_id__in=posted_ids,
                    product=ln.component,
                ),
            )
            InventoryService.restore_fifo_peels(mv, inbound, qty=take, already_restored=already)
            sources.append({"move": mv.pk, "qty": str(take), "unit_cost": str(mv.unit_cost or 0)})
            cost_total += take * d(mv.unit_cost)
            move_ids.append(inbound.pk)
            remaining -= take
        ln.sources, ln.movement_ids = sources, move_ids
        ln.cost_amount = money(cost_total)
        ln.unit_cost = unit4(cost_total / ln.qty)
        ln.save(update_fields=["sources", "movement_ids", "cost_amount", "unit_cost"])
        total += ln.cost_amount
        if ln.component.track_serial and ln.serial_numbers:
            SerialNumberService.transition(
                company=wo.company, product=ln.component, warehouse=ln.warehouse,
                numbers=[str(s).strip() for s in ln.serial_numbers if str(s).strip()],
                quantity=ln.qty, source=SerialNumber.Status.CONSUMED,
                target=SerialNumber.Status.AVAILABLE, user=user,
            )
            trace.release_serials(wo, ln.component, ln.serial_numbers)
        WorkOrderLine.objects.filter(pk=wl.pk).update(qty_returned=F("qty_returned") + ln.qty)
        wl.qty_returned = wl.qty_returned + ln.qty
    if d(wo.wip_value) - total < Decimal("-0.005"):
        raise rule(
            "Finished goods have already taken the cost of these materials, so they cannot come back. "
            "Reverse the production receipts first.",
            "MFG_REVERSAL_ORDER",
        )
    wo.cost_returned = money(d(wo.cost_returned) + total)
    wo.updated_by = user
    wo.save(update_fields=["cost_returned", "updated_at", "updated_by"])
    ret.status = DocumentStatus.POSTED
    ret.number = next_number(wo.company, "mfg_return", "MR")
    ret.doc_date = doc_date
    ret.posted_at = timezone.now()
    ret.updated_by = user
    ret.save(update_fields=["status", "number", "doc_date", "posted_at", "updated_by", "updated_at"])
    if posts_to_ledger(wo.company):
        from accounting.services import PostingService

        PostingService.post_mfg_wip(
            company=wo.company, source_type="MFG_RETURN", source_id=ret.pk, purpose="POST",
            entry_date=doc_date, amount=total, into_wip=False,
            narration=f"{ret.number} materials back from {wo.number or wo.pk}", user=user,
        )
    AuditService.log(
        action="mfg.return.posted", company=wo.company, user=user, entity_type="MaterialReturn",
        entity_id=str(ret.pk), description=f"{ret.number} for {wo.number or wo.pk}: {total}",
    )
    return ret


@transaction.atomic
def reverse_return(ret, user, reason) -> MaterialReturn:
    ret = MaterialReturn.objects.select_for_update().get(pk=ret.pk)
    wo = lock_work_order(ret.work_order_id)
    if ret.status != DocumentStatus.POSTED:
        raise rule("Only a posted return can be reversed.", "MFG_DOC_NOT_POSTED")
    if not (reason or "").strip():
        raise rule("Say why this return is being reversed.", "MFG_REASON_REQUIRED")
    if wo.status == WorkOrder.Status.CLOSED:
        raise rule("Reopen the closed work order before reversing documents on it.", "MFG_REVERSAL_ORDER")
    doc_date = assert_doc_date(wo.company, ret.doc_date, allow_soft_closed=True, label="Reversal")
    total = ZERO
    for ln in ret.lines.select_related("component", "wo_line", "warehouse").order_by("id"):
        for mid in ln.movement_ids or []:
            move = StockMovement.objects.select_related("product", "warehouse", "batch").get(pk=mid)
            if InventoryService.available_quantity(wo.company, move.product, move.warehouse, move.batch) < move.quantity:
                raise rule(
                    f"'{move.product.name}' from this return has already been used; it cannot be taken back out.",
                    "MFG_REVERSAL_ORDER",
                )
            InventoryService.unrestore_from_detail(move)
            InventoryService.post_movement(
                company=wo.company, product=move.product, warehouse=move.warehouse, batch=move.batch,
                movement_type=MovementType.MANUFACTURE_REVERSAL, quantity=-abs(move.quantity),
                unit_cost=move.unit_cost, user=user, reference_type="mfg_return_reverse",
                reference_id=str(ret.pk), movement_date=doc_date, reason=reason[:255],
            )
        if ln.component.track_serial and ln.serial_numbers:
            SerialNumberService.transition(
                company=wo.company, product=ln.component, warehouse=ln.warehouse,
                numbers=[str(s).strip() for s in ln.serial_numbers if str(s).strip()],
                quantity=ln.qty, source=SerialNumber.Status.AVAILABLE,
                target=SerialNumber.Status.CONSUMED, user=user,
            )
            trace.restore_serials(wo, ln.component, ln.serial_numbers)
        WorkOrderLine.objects.filter(pk=ln.wo_line_id).update(qty_returned=F("qty_returned") - ln.qty)
        total += ln.cost_amount
    wo.cost_returned = money(d(wo.cost_returned) - total)
    wo.updated_by = user
    wo.save(update_fields=["cost_returned", "updated_at", "updated_by"])
    if posts_to_ledger(wo.company):
        from accounting.services import PostingService

        PostingService.reverse_mfg_document(
            company=wo.company, source_type="MFG_RETURN", source_id=ret.pk, user=user, entry_date=doc_date,
        )
    ret.status = DocumentStatus.REVERSED
    ret.reversed_at = timezone.now()
    ret.reversed_by = user
    ret.reverse_reason = reason[:500]
    ret.save(update_fields=["status", "reversed_at", "reversed_by", "reverse_reason", "updated_at"])
    AuditService.log(
        action="mfg.return.reversed", company=wo.company, user=user, entity_type="MaterialReturn",
        entity_id=str(ret.pk), description=f"{ret.number}: {reason[:200]}",
    )
    return ret
