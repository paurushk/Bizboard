"""Work-order release / complete / cancel with BOM snapshot + optional WIP GL."""

from decimal import Decimal

from django.db import transaction

from core.exceptions import BusinessRuleError
from inventory.models import MovementType, SerialNumber, StockMovement
from inventory.services import InventoryService, InventoryValuationService, SerialNumberService

from .models import WorkOrder, WorkOrderLine


def _component_requirements(wo):
    snaps = list(wo.component_lines.select_related("component", "batch").all())
    if snaps:
        return [(line.component, line.qty, line) for line in snaps]
    return [
        (line.component, line.qty * wo.qty, None)
        for line in wo.bom.lines.select_related("component").all()
    ]


def _snapshot_bom(wo):
    wo.component_lines.all().delete()
    WorkOrderLine.objects.bulk_create(
        [
            WorkOrderLine(
                work_order=wo,
                component=line.component,
                qty_per_unit=line.qty,
                qty=line.qty * wo.qty,
            )
            for line in wo.bom.lines.select_related("component").all()
        ]
    )


def _issue_cost_total(wo) -> Decimal:
    total = Decimal("0")
    for move in StockMovement.objects.filter(
        company=wo.company,
        reference_type="work_order",
        reference_id=str(wo.id),
        movement_type=MovementType.MANUFACTURE_ISSUE,
    ):
        total += (move.unit_cost or Decimal("0")) * abs(move.quantity)
    return total


def _issue_batches(wo, component, qty, line=None):
    """BB-000723: explicit batch on WorkOrderLine or FEFO allocate."""
    if not component.track_batch:
        return [(getattr(line, "batch", None) if line else None, qty)]
    batch = getattr(line, "batch", None) if line else None
    if batch is not None:
        return [(batch, qty)]
    remaining = Decimal(str(qty))
    allocations = []
    warehouse = wo.warehouse or InventoryService.default_warehouse(wo.company)
    for lot in InventoryValuationService.fefo_batches(wo.company, component, warehouse):
        if remaining <= 0:
            break
        available = InventoryService.available_quantity(wo.company, component, warehouse, lot)
        take = min(remaining, available)
        if take > 0:
            allocations.append((lot, take))
            remaining -= take
    if remaining > 0:
        raise BusinessRuleError(
            f"Insufficient batched stock for component '{component.name}': short {remaining}."
        )
    if not allocations:
        raise BusinessRuleError(f"No stock batch is available for '{component.name}'.")
    return allocations


@transaction.atomic
def release_work_order(wo, user):
    from django.utils import timezone

    from reporting.gst_periods import assert_period_allows_money_amend

    # BB-000706: gate + JE on WO business date (fallback localdate).
    gate_date = wo.released_at or timezone.localdate()
    assert_period_allows_money_amend(wo.company, gate_date)
    if wo.status != WorkOrder.Status.DRAFT:
        raise BusinessRuleError("Only draft work orders can be released.")
    if wo.bom.status != wo.bom.Status.ACTIVE:
        raise BusinessRuleError("BOM must be ACTIVE to release a work order.")
    warehouse = wo.warehouse or InventoryService.default_warehouse(wo.company)
    wo.warehouse = warehouse
    _snapshot_bom(wo)
    requirements = _component_requirements(wo)
    if not requirements:
        raise BusinessRuleError("BOM has no component lines.")
    for component, qty, line in requirements:
        lot_payload = []
        for batch, take in _issue_batches(wo, component, qty, line):
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
        if line is not None and lot_payload:
            line.lot_allocations = lot_payload
            updates = ["lot_allocations"]
            if len(lot_payload) == 1:
                line.batch_id = lot_payload[0]["batch_id"]
                updates.append("batch")
            line.save(update_fields=updates)
    wo.status = WorkOrder.Status.RELEASED
    wo.released_at = wo.released_at or gate_date
    wo.updated_by = user
    wo.save(update_fields=["status", "warehouse", "released_at", "updated_at", "updated_by"])
    if wo.company.accounting_enabled:
        from accounting.services import PostingService

        PostingService.post_work_order_release(wo, _issue_cost_total(wo), user=user)
    return wo


@transaction.atomic
def complete_work_order(wo, user):
    from django.utils import timezone

    from reporting.gst_periods import assert_period_allows_money_amend

    # BB-000706: gate + JE on WO business date (fallback localdate).
    gate_date = wo.completed_at or timezone.localdate()
    assert_period_allows_money_amend(wo.company, gate_date)
    if wo.status != WorkOrder.Status.RELEASED:
        raise BusinessRuleError("Only released work orders can be completed.")
    warehouse = wo.warehouse or InventoryService.default_warehouse(wo.company)
    issue_cost = _issue_cost_total(wo)
    if issue_cost > 0 and wo.qty:
        unit_cost = (issue_cost / wo.qty).quantize(Decimal("0.0001"))
    else:
        unit_cost = Decimal("0")
        for component, qty, _line in _component_requirements(wo):
            unit_cost += (component.purchase_price or Decimal("0")) * qty
        if wo.qty:
            unit_cost = (unit_cost / wo.qty).quantize(Decimal("0.0001"))
    fg = wo.bom.product
    # BB-000723: register FG serials when track_serial.
    if fg.track_serial:
        SerialNumberService.receive(
            company=wo.company,
            product=fg,
            warehouse=warehouse,
            numbers=wo.serial_numbers,
            quantity=wo.qty,
            user=user,
        )
    InventoryService.post_movement(
        company=wo.company,
        product=fg,
        warehouse=warehouse,
        movement_type=MovementType.MANUFACTURE_RECEIPT,
        quantity=wo.qty,
        unit_cost=unit_cost,
        user=user,
        reference_type="work_order",
        reference_id=str(wo.id),
    )
    wo.status = WorkOrder.Status.COMPLETED
    wo.completed_at = wo.completed_at or gate_date
    wo.updated_by = user
    wo.save(update_fields=["status", "completed_at", "updated_at", "updated_by"])
    if wo.company.accounting_enabled:
        from accounting.services import PostingService

        PostingService.post_work_order_complete(wo, issue_cost or (unit_cost * wo.qty), user=user)
    return wo


@transaction.atomic
def cancel_work_order(wo, user):
    from django.utils import timezone

    from reporting.gst_periods import assert_period_allows_money_amend

    # BB-000706: cancel against WO business date, not wall-clock today.
    gate_date = wo.completed_at or wo.released_at or timezone.localdate()
    assert_period_allows_money_amend(wo.company, gate_date, allow_soft_closed=True)
    if wo.status not in (WorkOrder.Status.RELEASED, WorkOrder.Status.COMPLETED):
        raise BusinessRuleError("Only released or completed work orders can be cancelled.")
    warehouse = wo.warehouse or InventoryService.default_warehouse(wo.company)
    if wo.status == WorkOrder.Status.COMPLETED:
        # BB-000724: retire the specific MANUFACTURE_RECEIPT layer (not FIFO-oldest).
        for move in StockMovement.objects.filter(
            company=wo.company,
            reference_type="work_order",
            reference_id=str(wo.id),
            movement_type=MovementType.MANUFACTURE_RECEIPT,
        ):
            InventoryService.post_movement(
                company=wo.company,
                product=move.product,
                warehouse=move.warehouse or warehouse,
                batch=move.batch,
                movement_type=MovementType.ADJUSTMENT,
                quantity=-abs(move.quantity),
                unit_cost=move.unit_cost,
                user=user,
                reference_type="work_order_cancel",
                reference_id=str(wo.id),
            )
            InventoryService.retire_source_layers(move, abs(Decimal(str(move.quantity))))
            if move.product.track_serial and wo.serial_numbers:
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
            movement_type=MovementType.ADJUSTMENT,
            quantity=abs(move.quantity),
            unit_cost=move.unit_cost,
            user=user,
            reference_type="work_order_cancel",
            reference_id=str(wo.id),
        )
        InventoryService.restore_fifo_peels(move, inbound)
    if wo.company.accounting_enabled:
        from accounting.services import PostingService

        PostingService.reverse_work_order(wo, user=user)
    wo.status = WorkOrder.Status.CANCELLED
    wo.updated_by = user
    wo.save(update_fields=["status", "updated_at", "updated_by"])
    return wo
