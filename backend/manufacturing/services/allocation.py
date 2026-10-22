"""Which lots a component issue draws from (BB-000723, B8-010)."""

from decimal import Decimal

from inventory.models import BatchLot, StockBalance
from inventory.services import InventoryService, InventoryValuationService

from .common import rule


def lock_component_balances(company, warehouse, component):
    """B8-010: lock every balance row for this component and godown before planning an allocation.

    post_movement re-checks each row it writes, so this cannot overdraft; the lock only makes
    the plan below race-free, so a concurrent issue falls through to the next FEFO lot instead
    of failing on a stale read. Rows are locked in id order, which keeps two issues from
    deadlocking.
    """
    list(
        StockBalance.objects.select_for_update().filter(
            company=company, product=component, warehouse=warehouse,
        ).order_by("id")
    )


def allocate_batches(company, warehouse, component, qty, *, batch=None, lot_allocations=None):
    """Return ``[(batch_or_None, qty), ...]`` that add up to ``qty``.

    An explicit batch, then explicit lot allocations, then first-expiry-first-out.
    Products that do not track batches are one un-batched take.
    """
    qty = Decimal(str(qty))
    if not component.track_batch:
        return [(batch, qty)]
    lock_component_balances(company, warehouse, component)
    if batch is not None:
        available = InventoryService.available_quantity(company, component, warehouse, batch)
        if available < qty:
            raise rule(
                f"Insufficient stock in batch '{getattr(batch, 'batch_no', batch)}' "
                f"for '{component.name}': available {available}, required {qty}.",
                "MFG_SHORT_STOCK",
            )
        return [(batch, qty)]

    if lot_allocations:
        allocs = []
        for alloc in lot_allocations:
            b_id = alloc.get("batch_id")
            b_qty = Decimal(str(alloc.get("qty") or 0))
            if b_id and b_qty > 0:
                b_obj = BatchLot.objects.filter(company=company, pk=b_id, product_id=component.pk).first()
                if not b_obj:
                    raise rule(
                        f"Lot allocation batch {b_id} does not belong to '{component.name}'.",
                        "MFG_BAD_LOT_ALLOCATION",
                    )
                allocs.append((b_obj, b_qty))
        if allocs:
            tot = sum((q for _, q in allocs), Decimal("0"))
            if tot > qty:
                raise rule("Lot allocations exceed the required component quantity.", "MFG_BAD_LOT_ALLOCATION")
            if tot != qty:
                raise rule("Lot allocations must equal the required component quantity.", "MFG_BAD_LOT_ALLOCATION")
            return allocs

    remaining = qty
    allocations = []
    for lot in InventoryValuationService.fefo_batches(company, component, warehouse):
        if remaining <= 0:
            break
        available = InventoryService.available_quantity(company, component, warehouse, lot)
        take = min(remaining, available)
        if take > 0:
            allocations.append((lot, take))
            remaining -= take
    if remaining > 0:
        raise rule(
            f"Insufficient batched stock for component '{component.name}': short {remaining}.",
            "MFG_SHORT_STOCK",
        )
    if not allocations:
        raise rule(f"No stock batch is available for '{component.name}'.", "MFG_SHORT_STOCK")
    return allocations
