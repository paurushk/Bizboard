"""Genealogy: which input lots and serials went into which output (MFG-01, MFG-13).

Inputs are recorded when material is issued (output not yet known). When a production
receipt puts the output into stock, the open links of that work order are closed against
the output lot or serials. Reversing a document marks its links reversed; nothing is deleted.
"""

from decimal import Decimal

from django.utils import timezone

from inventory.models import TraceLink


def record_inputs(wo, *, document_type, document_id, component, batch=None, serials=None, qty=0):
    """One link for the lot (if any) and one per serial a component brings in."""
    serials = [str(s).strip() for s in (serials or []) if str(s).strip()]
    rows = []
    if serials:
        for number in serials:
            rows.append(TraceLink(
                company_id=wo.company_id, work_order_id=wo.pk, document_type=document_type,
                document_id=document_id, input_product=component, input_batch=batch,
                input_serial=number, output_product_id=wo.product_id, qty=Decimal("1"),
            ))
    else:
        rows.append(TraceLink(
            company_id=wo.company_id, work_order_id=wo.pk, document_type=document_type,
            document_id=document_id, input_product=component, input_batch=batch,
            output_product_id=wo.product_id, qty=Decimal(str(qty)),
        ))
    TraceLink.objects.bulk_create(rows)
    return rows


def link_outputs(wo, *, product=None, batch=None, serials=None):
    """Close the work order's open input links against the output lot (and serials)."""
    open_links = TraceLink.objects.filter(
        company_id=wo.company_id, work_order_id=wo.pk, reversed_at__isnull=True, output_batch__isnull=True,
    )
    if batch is not None:
        open_links.update(output_batch=batch, output_product=product or wo.product)
    serials = [str(s).strip() for s in (serials or []) if str(s).strip()]
    if serials:
        # Every output serial is made from the same inputs; record the pairing once per output serial
        # on the lot-level rows rather than exploding inputs x outputs.
        TraceLink.objects.filter(
            company_id=wo.company_id, work_order_id=wo.pk, reversed_at__isnull=True, output_serial="",
        ).update(output_serial=serials[0] if len(serials) == 1 else "")


def reverse_document(wo, *, document_type, document_id):
    """Mark the links a reversed document wrote as reversed."""
    return TraceLink.objects.filter(
        company_id=wo.company_id, work_order_id=wo.pk, document_type=document_type,
        document_id=document_id, reversed_at__isnull=True,
    ).update(reversed_at=timezone.now())


def reverse_work_order(wo):
    return TraceLink.objects.filter(
        company_id=wo.company_id, work_order_id=wo.pk, reversed_at__isnull=True,
    ).update(reversed_at=timezone.now())


def release_serials(wo, component, serials):
    """Serials that went back to stock are no longer part of this order's genealogy."""
    numbers = [str(s).strip() for s in (serials or []) if str(s).strip()]
    if not numbers:
        return 0
    return TraceLink.objects.filter(
        company_id=wo.company_id, work_order_id=wo.pk, input_product=component, input_serial__in=numbers,
        reversed_at__isnull=True,
    ).update(reversed_at=timezone.now())


def restore_serials(wo, component, serials):
    """Undo ``release_serials`` when the return that freed them is itself reversed."""
    numbers = [str(s).strip() for s in (serials or []) if str(s).strip()]
    if not numbers:
        return 0
    return TraceLink.objects.filter(
        company_id=wo.company_id, work_order_id=wo.pk, input_product=component, input_serial__in=numbers,
        reversed_at__isnull=False,
    ).update(reversed_at=None)


# --- recall queries (MFG-13) -------------------------------------------------------------------

MAX_DEPTH = 10


def _source_of(company, batch):
    """Where a received lot came from: the supplier document that put it into stock."""
    from inventory.models import MovementType, StockMovement

    move = StockMovement.objects.filter(
        company=company, batch=batch, movement_type__in=[MovementType.PURCHASE, MovementType.OPENING_STOCK],
    ).order_by("id").first()
    if move is None:
        return None
    info = {"movement_type": move.movement_type, "reference_type": move.reference_type, "reference_id": move.reference_id}
    try:
        if move.reference_type == "purchase_invoice":
            from purchases.models import PurchaseInvoice

            inv = PurchaseInvoice.objects.select_related("supplier").get(pk=move.reference_id, company=company)
            info.update(number=inv.number or inv.supplier_bill_number, supplier=inv.supplier.name)
        elif move.reference_type == "goods_receipt":
            from purchases.models import GoodsReceipt

            grn = GoodsReceipt.objects.select_related("supplier").get(pk=move.reference_id, company=company)
            info.update(number=grn.number, supplier=grn.supplier.name)
    except Exception:  # a deleted or foreign document must not break a recall query
        pass
    return info


def trace_back(company, batch):
    """Everything that went into ``batch``: its inputs, and theirs, down to supplier lots."""
    seen, out, frontier = {batch.pk}, [], [(batch, 0)]
    while frontier:
        lot, depth = frontier.pop(0)
        if depth >= MAX_DEPTH:
            continue
        links = TraceLink.objects.filter(
            company=company, output_batch=lot, reversed_at__isnull=True,
        ).select_related("input_product", "input_batch")
        for link in links:
            node = {
                "depth": depth + 1, "output_batch": lot.batch_no, "product": link.input_product.name,
                "batch": link.input_batch.batch_no if link.input_batch_id else "",
                "serial": link.input_serial, "qty": str(link.qty), "work_order": link.work_order_id,
            }
            if link.input_batch_id:
                node["source"] = _source_of(company, link.input_batch)
            out.append(node)
            if link.input_batch_id and link.input_batch_id not in seen:
                seen.add(link.input_batch_id)
                frontier.append((link.input_batch, depth + 1))
    return out


def trace_forward(company, batch):
    """Everything made from ``batch`` and every customer document that sent it out."""
    from inventory.models import MovementType, StockMovement

    seen, products, customers, frontier = {batch.pk}, [], [], [(batch, 0)]
    while frontier:
        lot, depth = frontier.pop(0)
        if depth >= MAX_DEPTH:
            continue
        for link in TraceLink.objects.filter(
            company=company, input_batch=lot, reversed_at__isnull=True, output_batch__isnull=False,
        ).select_related("output_batch", "output_product"):
            out_lot = link.output_batch
            products.append({
                "depth": depth + 1, "from_batch": lot.batch_no, "batch": out_lot.batch_no,
                "product": link.output_product.name if link.output_product_id else "",
                "work_order": link.work_order_id,
            })
            if out_lot.pk not in seen:
                seen.add(out_lot.pk)
                frontier.append((out_lot, depth + 1))
        for move in StockMovement.objects.filter(
            company=company, batch=lot, movement_type=MovementType.SALE,
        ).select_related("product"):
            customers.append(_customer_of(company, move, lot))
    return {"made_from_it": products, "sent_to": [c for c in customers if c]}


def _customer_of(company, move, lot):
    info = {"batch": lot.batch_no, "product": move.product.name, "qty": str(abs(move.quantity)),
            "date": str(move.movement_date), "document": move.reference_type, "document_id": move.reference_id}
    try:
        if move.reference_type == "sales_invoice":
            from sales.models import SalesInvoice

            inv = SalesInvoice.objects.select_related("customer").get(pk=move.reference_id, company=company)
            info.update(number=inv.number, customer=inv.customer.name if inv.customer_id else "")
        elif move.reference_type == "delivery_challan":
            from sales.models import DeliveryChallan

            ch = DeliveryChallan.objects.select_related("customer").get(pk=move.reference_id, company=company)
            info.update(number=ch.number, customer=ch.customer.name)
    except Exception:
        pass
    return info
