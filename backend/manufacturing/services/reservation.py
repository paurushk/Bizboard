"""Holds on stock for a released work order (MFG-10).

A hold lowers ``available`` (on hand minus reserved) so a sale cannot take what a work order
is waiting for. It never moves stock. Holds are rows with ``reference_type="work_order"`` and no
expiry; only the work order releases them: when material is issued, when the order closes,
is cancelled or is short-closed.
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from inventory.models import StockBalance, StockReservation
from inventory.services import InventoryService, InventoryValuationService

from .common import ZERO, d, resolve_issue_warehouse

REF = "work_order"


def _balance(company, warehouse, product, batch):
    row, _ = StockBalance.objects.get_or_create(
        company=company, warehouse=warehouse, product=product, batch=batch,
    )
    return StockBalance.objects.select_for_update().get(pk=row.pk)


def _hold(company, warehouse, product, batch, qty, wo, user):
    balance = _balance(company, warehouse, product, batch)
    balance.reserved = balance.reserved + qty
    balance.save(update_fields=["reserved"])
    StockReservation.objects.create(
        company=company, warehouse=warehouse, product=product, batch=batch, quantity=qty,
        expires_at=None, reference_type=REF, reference_id=str(wo.pk),
        created_by=user if getattr(user, "pk", None) else None,
        updated_by=user if getattr(user, "pk", None) else None,
    )


@transaction.atomic
def reserve_line(wo, line, user=None, qty=None) -> Decimal:
    """Hold up to ``qty`` (default: what the line still needs) of a component. Returns what was held.

    Holds only what is available; a shortage is not an error here (planning shows it).
    """
    company = wo.company
    need = d(qty) if qty is not None else line.qty_remaining
    if need <= 0 or line.principal_supplied:
        return ZERO
    component = line.component
    warehouse = resolve_issue_warehouse(wo, component, line=line)
    held = ZERO
    if component.track_batch:
        if line.source_batch_id or line.batch_id:
            lots = [line.source_batch or line.batch]
        else:
            lots = list(InventoryValuationService.fefo_batches(company, component, warehouse))
        for lot in lots:
            if need <= 0:
                break
            take = min(need, InventoryService.available_quantity(company, component, warehouse, lot))
            if take > 0:
                _hold(company, warehouse, component, lot, take, wo, user)
                need -= take
                held += take
    else:
        take = min(need, InventoryService.available_quantity(company, component, warehouse))
        if take > 0:
            _hold(company, warehouse, component, None, take, wo, user)
            held += take
    return held


@transaction.atomic
def reserve_work_order(wo, user=None) -> dict:
    """Hold every component line of a work order. Returns {component_id: qty held}."""
    out = {}
    for line in wo.component_lines.select_related("component", "batch", "source_batch").filter(alternate_of__isnull=True):
        out[line.component_id] = reserve_line(wo, line, user)
    return out


def _open_rows(wo, component=None):
    qs = StockReservation.objects.select_for_update().filter(
        company=wo.company, reference_type=REF, reference_id=str(wo.pk), released_at__isnull=True,
    )
    if component is not None:
        qs = qs.filter(product=component)
    return qs.order_by("id")


@transaction.atomic
def release_for_issue(wo, component, qty) -> Decimal:
    """Free up to ``qty`` of this order's hold on a component before it is issued.

    The issue itself checks ``available``, so the order's own hold has to be lifted first or
    it would block its own material.
    """
    remaining = d(qty)
    freed = ZERO
    for row in _open_rows(wo, component):
        if remaining <= 0:
            break
        take = min(remaining, row.quantity)
        balance = _balance(wo.company, row.warehouse, row.product, row.batch)
        balance.reserved = max(ZERO, balance.reserved - take)
        balance.save(update_fields=["reserved"])
        if take >= row.quantity:
            row.released_at = timezone.now()
            row.save(update_fields=["released_at", "updated_at"])
        else:
            row.quantity = row.quantity - take
            row.save(update_fields=["quantity", "updated_at"])
        remaining -= take
        freed += take
    return freed


@transaction.atomic
def release_all(wo) -> Decimal:
    """Free every hold the order still has (close, cancel, short-close)."""
    freed = ZERO
    for row in _open_rows(wo):
        balance = _balance(wo.company, row.warehouse, row.product, row.batch)
        balance.reserved = max(ZERO, balance.reserved - row.quantity)
        balance.save(update_fields=["reserved"])
        row.released_at = timezone.now()
        row.save(update_fields=["released_at", "updated_at"])
        freed += row.quantity
    return freed


def held_for(wo, component) -> Decimal:
    return sum(
        (r.quantity for r in StockReservation.objects.filter(
            company=wo.company, reference_type=REF, reference_id=str(wo.pk),
            product=component, released_at__isnull=True,
        )),
        ZERO,
    )
