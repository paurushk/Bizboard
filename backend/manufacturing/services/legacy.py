"""Work-order release / complete / cancel with BOM snapshot + optional WIP GL.

This is the original one-step flow: release issues every component at once, complete
receives the whole quantity. Companies keep it (``WorkOrder.issue_mode = AUTO_AT_RELEASE``)
until they switch to the document flow. Rev 2 fixes in this file:

* DEF-1: completion posts exactly the value it put into stock; paise left over go to the
  manufacturing variance account. A zero-cost completion is refused.
* DEF-2: components used up are CONSUMED (with trace links), not SCRAPPED.
* DEF-3: cancelling a completed order reverses with MANUFACTURE_REVERSAL, not ADJUSTMENT.
"""

from accounting.books import posts_to_ledger
import logging
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from core.exceptions import BusinessRuleError
from inventory.models import MovementType, SerialNumber, StockMovement
from inventory.services import InventoryService, InventoryValuationService, SerialNumberService

from manufacturing.models import Bom, WorkOrder, WorkOrderLine, WorkOrderOutput

from . import trace
from .allocation import allocate_batches
from .bom import assert_no_bom_cycle
from .common import money, rule

logger = logging.getLogger(__name__)

__all__ = [
    "assert_no_bom_cycle", "release_work_order", "complete_work_order", "cancel_work_order",
    "_issue_cost_total", "_snapshot_bom", "_component_requirements", "_issue_batches",
]

MIN_QTY_PER_UNIT = Decimal("0.001")


def _component_requirements(wo):
    # An alternate is a stand-in for its primary, not an extra requirement.
    snaps = [ln for ln in wo.component_lines.select_related("component", "batch").all() if ln.alternate_of_id is None]
    if snaps:
        return [(line.component, line.qty, line) for line in snaps]
    return [
        (line.component, line.qty * wo.qty, None)
        for line in wo.bom.lines.select_related("component").all()
    ]


def _snapshot_bom(wo):
    """Freeze the BOM's lines and planned outputs onto the work order (B8-019)."""
    if wo.bom_id is None:
        return
    if not wo.component_lines.exists():
        from .bom import snapshot_lines

        items = snapshot_lines(wo.bom, wo.qty, wo.planned_start or wo.released_at)
        # Lines in one alternate group are stand-ins for each other: the lowest priority number is
        # the one the order needs; the rest are kept so they can be issued in its place.
        primary_of = {}
        for item in items:
            grp = item["alternate_group"]
            if grp is not None:
                best = primary_of.get(grp)
                if best is None or item["alternate_priority"] < best["alternate_priority"]:
                    primary_of[grp] = item
        made = {}
        ordered = sorted(
            range(len(items)),
            key=lambda i: (items[i]["alternate_group"] is not None and primary_of[items[i]["alternate_group"]] is not items[i], i),
        )
        for i in ordered:
            item = items[i]
            per_unit = max(
                item["per_unit"].quantize(MIN_QTY_PER_UNIT, rounding=ROUND_HALF_UP), MIN_QTY_PER_UNIT,
            )
            grp = item["alternate_group"]
            is_alt = grp is not None and primary_of[grp] is not item
            made[i] = WorkOrderLine.objects.create(
                work_order=wo, company_id=wo.company_id, component=item["component"],
                qty_per_unit=per_unit, qty=item["qty"], unit=item["unit"], scrap_pct=item["scrap_pct"],
                issue_method=item["issue_method"], is_optional=item["is_optional"],
                alternate_group=grp, alternate_priority=item["alternate_priority"],
                source_warehouse=item["source_warehouse"],
                alternate_of=made[items.index(primary_of[grp])] if is_alt else None,
            )
    if not wo.planned_outputs.exists():
        bom = wo.bom
        scale = wo.qty / bom.output_qty
        WorkOrderOutput.objects.bulk_create([
            WorkOrderOutput(
                work_order=wo, company_id=wo.company_id, product=out.product, kind=out.kind,
                qty=(out.qty * scale).quantize(Decimal("0.001")), cost_share_pct=out.cost_share_pct,
                recovery_rate=out.recovery_rate, target_warehouse=out.target_warehouse,
            )
            for out in bom.outputs.select_related("product")
        ])


def _issue_cost_total(wo) -> Decimal:
    total = Decimal("0")
    for move in StockMovement.objects.filter(
        company=wo.company,
        reference_type="work_order",
        reference_id=str(wo.id),
        movement_type=MovementType.MANUFACTURE_ISSUE,
    ):
        total += (move.unit_cost or Decimal("0")) * abs(move.quantity)
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _issue_batches(wo, component, qty, line=None):
    """BB-000723: explicit batch or lot_allocations on WorkOrderLine or FEFO allocate."""
    warehouse = wo.warehouse or InventoryService.default_warehouse(wo.company)
    return allocate_batches(
        wo.company, warehouse, component, qty,
        batch=getattr(line, "batch", None) if line else None,
        lot_allocations=getattr(line, "lot_allocations", None) if line else None,
    )


@transaction.atomic
def release_work_order(wo, user, *, component_serials=None):
    wo = WorkOrder.objects.select_for_update().get(pk=wo.pk)
    from django.utils import timezone

    from reporting.gst_periods import assert_period_allows_money_amend

    # BB-000706: gate + JE on WO business date (fallback localdate).
    gate_date = wo.released_at or timezone.localdate()
    assert_period_allows_money_amend(wo.company, gate_date)
    if wo.status != WorkOrder.Status.DRAFT:
        raise BusinessRuleError("Only draft work orders can be released.")
    assert_no_bom_cycle(
        wo.company,
        wo.bom.product_id,
        list(wo.bom.lines.values_list("component_id", flat=True)),
        ignore_bom_id=wo.bom_id,
    )
    if wo.bom.status != wo.bom.Status.ACTIVE:
        raise BusinessRuleError("BOM must be ACTIVE to release a work order.")
    warehouse = wo.warehouse or InventoryService.default_warehouse(wo.company)
    wo.warehouse = warehouse
    _snapshot_bom(wo)
    serial_map = {}
    if isinstance(component_serials, dict):
        serial_map = {str(k): v for k, v in component_serials.items()}
    if serial_map:
        for line in wo.component_lines.all():
            serials = serial_map.get(str(line.component_id)) or serial_map.get(line.component_id)
            if serials:
                line.serial_numbers = list(serials)
                line.save(update_fields=["serial_numbers"])
    requirements = _component_requirements(wo)
    if not requirements:
        raise BusinessRuleError("BOM has no component lines.")
    # B8-008: BOM explosion is single-level only -- a component that is
    # itself a manufactured sub-assembly (has its own ACTIVE BOM) is never
    # exploded into its own materials. Issuing from finished stock of that
    # sub-assembly is fine if it exists; silently proceeding when it
    # doesn't would issue negative/short stock with no explanation. Fail
    # loudly and specifically instead of letting a generic stock-shortage
    # error (or a negative-stock issue, if allowed) obscure the real cause.
    subassembly_ids = {
        pk
        for pk in Bom.objects.filter(
            company=wo.company,
            product_id__in=[component.pk for component, _qty, _line in requirements],
            status=Bom.Status.ACTIVE,
        ).values_list("product_id", flat=True)
    }
    if subassembly_ids:
        for component, qty, _line in requirements:
            if component.pk not in subassembly_ids:
                continue
            available = InventoryService.available_quantity(wo.company, component, warehouse)
            if available < qty:
                raise BusinessRuleError(
                    f"'{component.name}' is itself a manufactured sub-assembly (has an "
                    f"active BOM) — this app does not explode multi-level BOMs. Only "
                    f"{available} is available against {qty} required; manufacture it "
                    f"via its own work order first, or reduce this work order's quantity."
                )
    for component, qty, line in requirements:
        lot_payload = []
        plan = _issue_batches(wo, component, qty, line)
        for batch, take in plan:
            unit_cost = InventoryValuationService.unit_cost(
                wo.company, component, warehouse, batch=batch
            )
            InventoryService.post_movement(
                company=wo.company,
                product=component,
                warehouse=warehouse,
                batch=batch,
                movement_type=MovementType.MANUFACTURE_ISSUE,
                quantity=take,
                unit_cost=unit_cost,
                user=user,
                reference_type="work_order",
                reference_id=str(wo.id),
            )
            if batch is not None:
                lot_payload.append(
                    {"batch_id": batch.pk, "batch_no": batch.batch_no, "qty": str(take)}
                )
        comp_serials = []
        if component.track_serial:
            comp_serials = getattr(line, "serial_numbers", []) if line else []
            if not comp_serials:
                raise BusinessRuleError(
                    f"Serial numbers are required to issue '{component.name}'."
                )
            # DEF-2: used up, not scrapped.
            SerialNumberService.transition(
                company=wo.company,
                product=component,
                warehouse=warehouse,
                numbers=comp_serials,
                quantity=qty,
                source=SerialNumber.Status.AVAILABLE,
                target=SerialNumber.Status.CONSUMED,
                user=user,
            )
        if comp_serials:
            trace.record_inputs(
                wo, document_type="work_order", document_id=wo.pk, component=component,
                serials=comp_serials, qty=qty,
            )
        else:
            for batch, take in plan:
                trace.record_inputs(
                    wo, document_type="work_order", document_id=wo.pk, component=component,
                    batch=batch, qty=take,
                )
        if line is not None:
            updates = ["qty_issued"]
            line.qty_issued = line.qty
            if lot_payload:
                line.lot_allocations = lot_payload
                updates.append("lot_allocations")
                if len(lot_payload) == 1:
                    line.batch_id = lot_payload[0]["batch_id"]
                    updates.append("batch")
            line.save(update_fields=updates)
    wo.status = WorkOrder.Status.RELEASED
    if wo.released_at is None:
        wo.released_at = timezone.localdate()
    issue_cost = _issue_cost_total(wo)
    wo.cost_issued = issue_cost
    wo.updated_by = user
    wo.save(update_fields=[
        "status", "warehouse", "released_at", "cost_issued", "updated_at", "updated_by",
    ])
    if posts_to_ledger(wo.company):
        from accounting.services import PostingService

        PostingService.post_work_order_release(wo, issue_cost, user=user)
    return wo


@transaction.atomic
def complete_work_order(wo, user):
    """One receipt of the full quantity for the primary finished good.

    B8-009 note: by-products, co-products and scrap are handled by the document flow
    (ProductionReceipt). This legacy path still loads 100 % of the issue cost onto the
    primary finished good.
    """
    wo = WorkOrder.objects.select_for_update().get(pk=wo.pk)
    from django.utils import timezone

    from reporting.gst_periods import assert_period_allows_money_amend

    # BB-000706: gate + JE on WO business date (fallback localdate).
    gate_date = wo.completed_at or timezone.localdate()
    assert_period_allows_money_amend(wo.company, gate_date)
    if wo.status != WorkOrder.Status.RELEASED:
        raise BusinessRuleError("Only released work orders can be completed.")
    warehouse = wo.warehouse or InventoryService.default_warehouse(wo.company)
    issue_cost = _issue_cost_total(wo)
    if issue_cost <= 0:
        # DEF-1 / D-6: no stock value to carry onto the finished good. Stock would appear from
        # nowhere while the books showed nothing. Cost the components first.
        raise rule(
            "These materials have no cost on record, so the finished goods cannot be valued. "
            "Add the cost to the materials (an opening-stock or purchase cost) and try again.",
            "MFG_ZERO_COST_COMPLETE",
        )
    unit_cost = (issue_cost / wo.qty).quantize(Decimal("0.0001"))
    fg = wo.bom.product
    batch = getattr(wo, "batch", None)
    if fg.track_batch and batch is None:
        from inventory.models import BatchLot

        batch_number = getattr(wo, "batch_no", None) or f"WO-{wo.id}"
        wo_exp = getattr(wo, "exp_date", None)
        wo_mfg = getattr(wo, "mfg_date", None) or wo.completed_at or gate_date
        batch, created = BatchLot.objects.get_or_create(
            company=wo.company,
            product=fg,
            batch_no=batch_number,
            defaults={
                "expiry_date": wo_exp,
                "manufacturing_date": wo_mfg,
                "created_by": user,
                "updated_by": user,
            },
        )
        if not created:
            lot_updates = []
            if wo_exp and batch.expiry_date and batch.expiry_date != wo_exp:
                raise BusinessRuleError(
                    f"Batch {batch_number} already exists with expiry {batch.expiry_date}; "
                    f"entered {wo_exp} does not match."
                )
            elif wo_exp and not batch.expiry_date:
                batch.expiry_date = wo_exp
                lot_updates.append("expiry_date")
            if wo_mfg and batch.manufacturing_date and batch.manufacturing_date != wo_mfg:
                raise BusinessRuleError(
                    f"Batch {batch_number} already exists with mfg date {batch.manufacturing_date}; "
                    f"entered {wo_mfg} does not match."
                )
            elif wo_mfg and not batch.manufacturing_date:
                batch.manufacturing_date = wo_mfg
                lot_updates.append("manufacturing_date")
            if lot_updates:
                batch.updated_by = user
                lot_updates.extend(["updated_by", "updated_at"])
                batch.save(update_fields=lot_updates)
        wo.batch = batch
        wo.batch_no = batch_number
    # BB-000723: register FG serials when track_serial.
    if fg.track_serial:
        SerialNumberService.receive(
            company=wo.company,
            product=fg,
            warehouse=warehouse,
            numbers=wo.serial_numbers,
            quantity=wo.qty,
            user=user,
            allow_reactivate_scrap=True,
        )
    InventoryService.post_movement(
        company=wo.company,
        product=fg,
        warehouse=warehouse,
        batch=batch,
        movement_type=MovementType.MANUFACTURE_RECEIPT,
        quantity=wo.qty,
        unit_cost=unit_cost,
        user=user,
        reference_type="work_order",
        reference_id=str(wo.id),
    )
    # DEF-1: the books get exactly what went into stock (qty x 4dp unit cost, to the paisa);
    # whatever the rounding left over goes to manufacturing variance so WIP ends at zero.
    stock_value = money(unit_cost * wo.qty)
    leftover = issue_cost - stock_value
    wo.status = WorkOrder.Status.COMPLETED
    wo.completed_at = wo.completed_at or gate_date
    wo.qty_completed = wo.qty
    wo.cost_received = stock_value
    wo.cost_variance = leftover
    wo.updated_by = user
    wo.save(update_fields=[
        "status", "completed_at", "batch", "batch_no", "qty_completed", "cost_received",
        "cost_variance", "updated_at", "updated_by",
    ])
    trace.link_outputs(wo, product=fg, batch=batch, serials=wo.serial_numbers if fg.track_serial else None)
    if posts_to_ledger(wo.company):
        from accounting.services import PostingService

        PostingService.post_work_order_complete(wo, stock_value, user=user)
        if leftover != 0:
            PostingService.post_mfg_variance(
                company=wo.company, source_type="WORK_ORDER", source_id=wo.id,
                purpose="COMPLETE_ROUND", entry_date=wo.completed_at, amount=leftover,
                narration=f"WO-{wo.id} rounding", user=user,
            )
    return wo


@transaction.atomic
def cancel_work_order(wo, user):
    wo = WorkOrder.objects.select_for_update().get(pk=wo.pk)
    from django.utils import timezone

    from reporting.gst_periods import assert_period_allows_money_amend

    # BB-000706: cancel against WO business date, not wall-clock today.
    gate_date = wo.completed_at or wo.released_at or timezone.localdate()
    assert_period_allows_money_amend(wo.company, gate_date, allow_soft_closed=True)
    if wo.status not in (WorkOrder.Status.RELEASED, WorkOrder.Status.COMPLETED):
        raise BusinessRuleError("Only released or completed work orders can be cancelled.")
    warehouse = wo.warehouse or InventoryService.default_warehouse(wo.company)
    if wo.status == WorkOrder.Status.COMPLETED:
        # CR-014: Ensure finished goods have not already been consumed or sold before reversing
        fg_moves = list(
            StockMovement.objects.filter(
                company=wo.company,
                reference_type="work_order",
                reference_id=str(wo.id),
                movement_type=MovementType.MANUFACTURE_RECEIPT,
            )
        )
        for move in fg_moves:
            avail = InventoryService.available_quantity(
                wo.company,
                move.product,
                warehouse=move.warehouse or warehouse,
                batch=move.batch,
            )
            if avail < abs(move.quantity):
                raise BusinessRuleError(
                    f"Cannot cancel work order: finished goods for '{move.product.name}' "
                    f"have already been issued or sold (available {avail}, required {abs(move.quantity)})."
                )
        # BB-000724: retire the specific MANUFACTURE_RECEIPT layer (not FIFO-oldest).
        for move in fg_moves:
            InventoryService.post_movement(
                company=wo.company,
                product=move.product,
                warehouse=move.warehouse or warehouse,
                batch=move.batch,
                movement_type=MovementType.MANUFACTURE_REVERSAL,
                quantity=-abs(move.quantity),
                unit_cost=move.unit_cost,
                user=user,
                reference_type="work_order_cancel",
                reference_id=str(wo.id),
            )
            InventoryService.retire_source_layers(move, abs(Decimal(str(move.quantity))))
            if move.product.track_serial and wo.serial_numbers:
                # Scrap unused FG serials so they are not sellable after the
                # receipt is reversed. SerialNumberService.receive reactivates
                # SCRAPPED numbers on a later complete (reuse is not permanent).
                SerialNumberService.transition(
                    company=wo.company,
                    product=move.product,
                    warehouse=move.warehouse or warehouse,
                    numbers=wo.serial_numbers,
                    quantity=wo.qty,
                    source=SerialNumber.Status.AVAILABLE,
                    target=SerialNumber.Status.SCRAPPED,
                    user=user,
                )
    for move in StockMovement.objects.filter(
        company=wo.company,
        reference_type="work_order",
        reference_id=str(wo.id),
        movement_type=MovementType.MANUFACTURE_ISSUE,
    ):
        inbound = InventoryService.post_movement(
            company=wo.company,
            product=move.product,
            warehouse=move.warehouse or warehouse,
            batch=move.batch,
            movement_type=MovementType.MANUFACTURE_REVERSAL,
            quantity=abs(move.quantity),
            unit_cost=move.unit_cost,
            user=user,
            reference_type="work_order_cancel",
            reference_id=str(wo.id),
        )
        InventoryService.restore_fifo_peels(move, inbound)
        matching_lines = wo.component_lines.filter(component=move.product)
        all_comp_serials = []
        seen = set()
        for cline in matching_lines:
            for serial in getattr(cline, "serial_numbers", None) or []:
                key = str(serial).strip()
                if key and key not in seen:
                    seen.add(key)
                    all_comp_serials.append(serial)
        if move.product.track_serial and all_comp_serials:
            SerialNumberService.transition(
                company=wo.company,
                product=move.product,
                warehouse=move.warehouse or warehouse,
                numbers=all_comp_serials,
                quantity=len(all_comp_serials),
                source=SerialNumber.Status.CONSUMED,
                target=SerialNumber.Status.AVAILABLE,
                user=user,
            )
            for cline in matching_lines:
                cline.serial_numbers = []
                cline.save(update_fields=["serial_numbers"])
    if posts_to_ledger(wo.company):
        from accounting.services import PostingService

        PostingService.reverse_work_order(wo, user=user)
    trace.reverse_work_order(wo)
    wo.status = WorkOrder.Status.CANCELLED
    wo.updated_by = user
    wo.save(update_fields=["status", "updated_at", "updated_by"])
    return wo
