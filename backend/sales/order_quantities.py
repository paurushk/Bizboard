"""Quantities a sales order still owes or still holds, derived from its documents.

The line counters (``shipped_quantity``, ``invoiced_quantity``) move when a draft challan or
invoice is created, so they say what has been *taken*, not what has *left the building*. Stock
reservations move on completion, and reservations carry no order reference. Anything that has
to reason about a reservation therefore reads the documents:

- a COMPLETED challan released its share of the reservation when it completed;
- an invoice made straight from the order (``source_order``) releases its share when it completes;
- an invoice made from a challan released nothing, its challan already did.

``order_still_held`` is the one definition of "reserved for this order right now". The invoice
completion, the failed-stop release, the cancel, the stock rebuild and the unit-change guard
all call it, so they cannot drift apart.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

HOLDING_STATUSES = ("CONFIRMED", "PARTIALLY_CONVERTED")  # statuses that can hold stock; ``stock_held`` decides
_ZERO = Decimal("0")


def _qty(value) -> Decimal:
    return Decimal(str(value or 0))


def fmt_qty(value) -> str:
    """A quantity as people write it: ``6`` not ``6.000``, ``2.5`` not ``2.500``."""
    d = _qty(value)
    text = format(d.normalize(), "f")
    return text if "." not in text else text.rstrip("0").rstrip(".")


def ordered_by_product(order) -> dict[int, Decimal]:
    out: dict[int, Decimal] = defaultdict(lambda: _ZERO)
    for line in order.items.all():
        out[line.product_id] += _qty(line.quantity)
    return dict(out)


def shipped_by_product(order, *, completed_only: bool = True) -> dict[int, Decimal]:
    """Quantity on the order's challans (completed ones only by default)."""
    from .models import DeliveryChallan, DeliveryChallanItem

    statuses = (
        [DeliveryChallan.Status.COMPLETED]
        if completed_only
        else [DeliveryChallan.Status.DRAFT, DeliveryChallan.Status.COMPLETED]
    )
    out: dict[int, Decimal] = defaultdict(lambda: _ZERO)
    rows = DeliveryChallanItem.objects.filter(
        challan__company_id=order.company_id,
        challan__sales_order_id=order.pk,
        challan__status__in=statuses,
    ).values_list("product_id", "quantity")
    for product_id, quantity in rows:
        out[product_id] += _qty(quantity)
    # Goods that came back on a completed challan return are no longer shipped: the order owes them again.
    for product_id, quantity in returned_by_product(order).items():
        if product_id in out:
            out[product_id] = max(_ZERO, out[product_id] - quantity)
    return dict(out)


def returned_by_product(order) -> dict[int, Decimal]:
    """Quantity that came back on completed challan returns against this order's challans."""
    from .models import DeliveryChallanReturn, DeliveryChallanReturnItem

    out: dict[int, Decimal] = defaultdict(lambda: _ZERO)
    rows = DeliveryChallanReturnItem.objects.filter(
        challan_return__company_id=order.company_id,
        challan_return__challan__sales_order_id=order.pk,
        challan_return__status=DeliveryChallanReturn.Status.COMPLETED,
    ).values_list("product_id", "quantity")
    for product_id, quantity in rows:
        out[product_id] += _qty(quantity)
    return dict(out)


def invoiced_directly_by_product(order, *, exclude_invoice_id=None) -> dict[int, Decimal]:
    """Quantity on completed invoices made straight from the order (not via a challan)."""
    from .models import SalesInvoice, SalesItem

    qs = SalesItem.objects.filter(
        invoice__company_id=order.company_id,
        invoice__source_order_id=order.pk,
        invoice__status__in=(SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED),
    )
    if exclude_invoice_id is not None:
        qs = qs.exclude(invoice_id=exclude_invoice_id)
    out: dict[int, Decimal] = defaultdict(lambda: _ZERO)
    for product_id, quantity in qs.values_list("product_id", "quantity"):
        out[product_id] += _qty(quantity)
    return dict(out)


def order_still_held(order, *, exclude_invoice_id=None) -> dict[int, Decimal]:
    """Per product: the quantity still reserved for ``order``.

    Only an order that holds a reservation (``stock_held``, set when it is confirmed) holds
    anything: the status alone cannot say it, because an unconfirmed draft can become "partly
    processed" without ever reserving stock. The held quantity is what was ordered, less what
    completed challans shipped, less what completed direct invoices billed. A draft invoice or
    draft challan still holds its share until it completes. ``exclude_invoice_id`` leaves out an
    invoice that is being completed right now.
    """
    if not getattr(order, "stock_held", False) or getattr(order, "status", None) == "CANCELLED":
        return {}
    ordered = ordered_by_product(order)
    shipped = shipped_by_product(order)
    invoiced = invoiced_directly_by_product(order, exclude_invoice_id=exclude_invoice_id)
    held: dict[int, Decimal] = {}
    for product_id, qty in ordered.items():
        left = qty - shipped.get(product_id, _ZERO) - invoiced.get(product_id, _ZERO)
        if left > 0:
            held[product_id] = left
    return held


def order_remaining(order) -> dict[int, Decimal]:
    """Per product: quantity not yet taken by any live challan or invoice from this order.

    Unlike ``order_still_held`` this counts drafts, because a draft already claims its quantity:
    a second document may not take the same units. Challan-sourced and direct invoices are not
    both counted for the same units (an invoice made from a challan carries the challan's
    quantity, which the challan already claims).
    """
    from .models import SalesInvoice, SalesItem

    ordered = ordered_by_product(order)
    shipped = shipped_by_product(order, completed_only=False)
    direct: dict[int, Decimal] = defaultdict(lambda: _ZERO)
    rows = SalesItem.objects.filter(
        invoice__company_id=order.company_id,
        invoice__source_order_id=order.pk,
    ).exclude(invoice__status=SalesInvoice.Status.CANCELLED).values_list("product_id", "quantity")
    for product_id, quantity in rows:
        direct[product_id] += _qty(quantity)
    remaining: dict[int, Decimal] = {}
    for product_id, qty in ordered.items():
        left = qty - shipped.get(product_id, _ZERO) - direct.get(product_id, _ZERO)
        remaining[product_id] = left if left > 0 else _ZERO
    return remaining


def fulfilment_state(order) -> str:
    """Read-only label state for list and detail screens: ``none``, ``shipped_not_invoiced`` or ``invoiced``.

    Works on prefetched ``challans`` (with ``converted_invoice``) and ``split_invoices`` so a page
    of orders costs no query per row. ``invoiced`` means a live invoice exists for the order;
    ``shipped_not_invoiced`` means a challan completed and no live invoice covers it yet.
    """
    from .models import DeliveryChallan, SalesInvoice

    live = (SalesInvoice.Status.DRAFT, SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED)
    invoice = getattr(order, "converted_invoice", None)
    if invoice is not None and invoice.status in live:
        return "invoiced"
    if any(inv.status in live for inv in order.split_invoices.all()):
        return "invoiced"
    shipped = False
    for challan in order.challans.all():
        if challan.status != DeliveryChallan.Status.COMPLETED:
            continue
        converted = challan.converted_invoice
        if converted is not None and converted.status in live:
            return "invoiced"
        shipped = True
    return "shipped_not_invoiced" if shipped else "none"


# ---------------------------------------------------------------------------
# Documents are the truth; the line counters are a cache of them
# ---------------------------------------------------------------------------


def invoices_for_order(order, *, include_cancelled: bool = False):
    """Every invoice that carries goods of ``order``, however it was made.

    An order can be billed directly (``source_order``), through a challan
    (``DeliveryChallan.converted_invoice``), and ``converted_invoice`` points at the latest of
    them. A partly shipped order can have several. Read this, not the single pointer (H-13).
    """
    from django.db.models import Q

    from .models import SalesInvoice

    condition = Q(source_order_id=order.pk) | Q(source_challans__sales_order_id=order.pk)
    if getattr(order, "converted_invoice_id", None):
        condition |= Q(pk=order.converted_invoice_id)
    qs = SalesInvoice.objects.filter(company_id=order.company_id).filter(condition)
    if not include_cancelled:
        qs = qs.exclude(status=SalesInvoice.Status.CANCELLED)
    return qs.distinct()


def live_challans_for_order(order):
    from .models import DeliveryChallan

    return DeliveryChallan.objects.filter(company_id=order.company_id, sales_order_id=order.pk).exclude(
        status=DeliveryChallan.Status.CANCELLED
    )


def _distribute(lines, by_product: dict[int, Decimal]) -> dict[int, Decimal]:
    """Spread per-product totals over the order's lines in id order, never above a line's quantity.

    Any overflow (a document that took more than the order owes) lands on the last line of that
    product so no quantity is lost from the counters.
    """
    left = dict(by_product)
    out: dict[int, Decimal] = {}
    by_prod_lines: dict[int, list] = defaultdict(list)
    for line in lines:
        by_prod_lines[line.product_id].append(line)
    for product_id, product_lines in by_prod_lines.items():
        amount = left.get(product_id, _ZERO)
        for index, line in enumerate(product_lines):
            capacity = _qty(line.quantity)
            take = amount if index == len(product_lines) - 1 else min(capacity, amount)
            out[line.pk] = take
            amount -= take
    return out


def sync_order_counters(order) -> None:
    """Rewrite ``shipped_quantity`` and ``invoiced_quantity`` from the order's live documents.

    ``shipped_quantity`` = quantity on non-cancelled challans (draft claims it, completed has
    shipped it). ``invoiced_quantity`` = quantity on non-cancelled invoices made straight from
    the order. An invoice made from a challan carries the challan's quantity, which the challan
    already counts, so it is not added again. Calling this after any document change keeps the
    counters from drifting (deleting a draft, cancelling, editing quantities).
    """
    from .models import SalesInvoice, SalesItem

    lines = list(order.items.order_by("id"))
    if not lines:
        return
    shipped = shipped_by_product(order, completed_only=False)
    direct: dict[int, Decimal] = defaultdict(lambda: _ZERO)
    rows = SalesItem.objects.filter(
        invoice__company_id=order.company_id, invoice__source_order_id=order.pk
    ).exclude(invoice__status=SalesInvoice.Status.CANCELLED).values_list("product_id", "quantity")
    for product_id, quantity in rows:
        direct[product_id] += _qty(quantity)
    shipped_by_line = _distribute(lines, shipped)
    invoiced_by_line = _distribute(lines, dict(direct))
    for line in lines:
        new_shipped = shipped_by_line.get(line.pk, _ZERO)
        new_invoiced = invoiced_by_line.get(line.pk, _ZERO)
        if _qty(line.shipped_quantity) != new_shipped or _qty(line.invoiced_quantity) != new_invoiced:
            line.shipped_quantity = new_shipped
            line.invoiced_quantity = new_invoiced
            line.save(update_fields=["shipped_quantity", "invoiced_quantity"])


def line_remaining(line) -> Decimal:
    """Quantity of one order line not yet taken by any live challan or direct invoice."""
    left = _qty(line.quantity) - _qty(line.shipped_quantity) - _qty(line.invoiced_quantity)
    return left if left > 0 else _ZERO


def recompute_order_status(order, user=None, *, allow_reopen: bool = False) -> str:
    """Set the order's status from what has completed, once a challan or invoice completes.

    - everything taken, nothing still in draft, and something completed: ``CONVERTED``;
    - something completed but not all (or a draft is still pending): ``PARTIALLY_CONVERTED``;
    - otherwise unchanged. A cancelled order is never touched.
    ``allow_reopen`` lets a ``CONVERTED`` order fall back when its last document is cancelled.
    Counters are synced first so the answer never rests on stale numbers.
    """
    from .models import DeliveryChallan, SalesInvoice, SalesOrder

    if order.status == SalesOrder.Status.CANCELLED:
        return order.status
    sync_order_counters(order)
    lines = list(order.items.all())
    taken_all = bool(lines) and all(
        _qty(line.shipped_quantity) + _qty(line.invoiced_quantity) >= _qty(line.quantity) for line in lines
    )
    challans = list(live_challans_for_order(order).values_list("status", flat=True))
    invoices = list(invoices_for_order(order).values_list("status", flat=True))
    live_drafts = DeliveryChallan.Status.DRAFT in challans or SalesInvoice.Status.DRAFT in invoices
    # A challan whose goods all came back no longer counts as shipped.
    shipped_net = sum(shipped_by_product(order, completed_only=True).values(), _ZERO)
    completed_any = (DeliveryChallan.Status.COMPLETED in challans and shipped_net > 0) or any(
        status in (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED) for status in invoices
    )
    target = order.status
    live_any = bool(challans) or bool(invoices)
    if completed_any and taken_all and not live_drafts:
        target = SalesOrder.Status.CONVERTED
    elif completed_any and (
        order.status
        in (
            SalesOrder.Status.DRAFT,
            SalesOrder.Status.CONFIRMED,
            SalesOrder.Status.PARTIALLY_CONVERTED,
        )
        or (allow_reopen and order.status == SalesOrder.Status.CONVERTED)
    ):
        target = SalesOrder.Status.PARTIALLY_CONVERTED
    elif not completed_any and not live_any and (
        order.status == SalesOrder.Status.PARTIALLY_CONVERTED
        or (allow_reopen and order.status == SalesOrder.Status.CONVERTED)
    ):
        # Everything that was taken has been given back (drafts deleted or cancelled): the order
        # is where it started, confirmed if it holds stock, still a draft if it never did.
        target = SalesOrder.Status.CONFIRMED if order.stock_held else SalesOrder.Status.DRAFT
    fields = []
    if target != order.status:
        order.status = target
        fields.append("status")
    # ``converted_invoice`` is the latest live invoice. Deleting or cancelling the latest one must
    # not leave the pointer empty while an older invoice is still alive.
    live_ids = list(invoices_for_order(order).order_by("-id").values_list("pk", flat=True))
    if live_ids and order.converted_invoice_id not in live_ids:
        order.converted_invoice_id = live_ids[0]
        fields.append("converted_invoice")
    if fields:
        if user is not None:
            order.updated_by = user
            fields.append("updated_by")
        order.save(update_fields=fields + ["updated_at"])
    return order.status


def remaining_excluding_challan(order, challan=None) -> dict[int, Decimal]:
    """Per product: quantity a challan of this order may still carry.

    ``challan`` is the one being written: its own current lines are not counted against it, so
    editing a draft challan does not compete with itself.
    """
    from .models import DeliveryChallanItem

    remaining = order_remaining(order)
    if challan is not None and challan.pk:
        own: dict[int, Decimal] = defaultdict(lambda: _ZERO)
        for product_id, quantity in DeliveryChallanItem.objects.filter(challan_id=challan.pk).values_list(
            "product_id", "quantity"
        ):
            own[product_id] += _qty(quantity)
        for product_id, quantity in own.items():
            remaining[product_id] = remaining.get(product_id, _ZERO) + quantity
    return remaining
