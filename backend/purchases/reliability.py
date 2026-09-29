"""Lead time and fill rate. Two numbers, no score and no rank."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum

from purchases.models import GoodsReceipt, GoodsReceiptItem, PurchaseOrder, PurchaseOrderItem


def supply_metrics(company, supplier, product) -> dict:
    receipts = list(
        GoodsReceipt.objects.filter(
            company=company,
            supplier=supplier,
            status=GoodsReceipt.Status.COMPLETED,
            purchase_order__isnull=False,
            purchase_order__status=PurchaseOrder.Status.CONVERTED,
            items__product=product,
        )
        .select_related("purchase_order")
        .distinct()
    )
    samples = []
    for receipt in receipts:
        order = receipt.purchase_order
        if order is None or order.status == PurchaseOrder.Status.CANCELLED:
            continue
        samples.append((receipt.receipt_date - order.order_date).days)
    lead_time = None
    if samples:
        lead_time = str((sum(samples) / len(samples)))

    # Only converted orders count as "ordered" — a draft/abandoned PO never
    # placed a real commitment, matching the same convention supplier price
    # history already uses (purchases/views.py).
    ordered = PurchaseOrderItem.objects.filter(
        company=company,
        product=product,
        purchase_order__supplier=supplier,
        purchase_order__status=PurchaseOrder.Status.CONVERTED,
    ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
    received = GoodsReceiptItem.objects.filter(
        goods_receipt__in=receipts, product=product
    ).aggregate(total=Sum("quantity_received"))["total"] or Decimal("0")
    ordered = Decimal(str(ordered))
    received = Decimal(str(received))
    fill_rate = None
    over_receipt = False
    if ordered > 0:
        raw = received / ordered
        over_receipt = raw > 1
        shown = min(raw, Decimal("1"))
        fill_rate = str(shown.quantize(Decimal("0.0001")))
    return {
        "lead_time_days": lead_time,
        "fill_rate": fill_rate,
        "over_receipt": over_receipt,
        "lead_time_samples": len(samples),
    }


def last_completed_purchase_rate(company, supplier, product, *, exclude_invoice_id=None) -> dict | None:
    """Most recent COMPLETED purchase invoice line for this supplier+product.

    Same underlying query as the supplier price-history endpoint
    (purchases.views.SupplierPriceHistoryView) — this is a read of that same
    history, not a second price-history mechanism. Returns None on cold start
    (no prior completed purchase) rather than erroring.
    """
    from purchases.models import PurchaseInvoice, PurchaseItem

    if supplier is None or product is None:
        return None
    qs = (
        PurchaseItem.objects.filter(
            company=company,
            product=product,
            invoice__supplier=supplier,
            invoice__status=PurchaseInvoice.Status.COMPLETED,
        )
        .select_related("invoice")
        .order_by("-invoice__invoice_date", "-id")
    )
    if exclude_invoice_id:
        qs = qs.exclude(invoice_id=exclude_invoice_id)
    item = qs.first()
    if item is None:
        return None
    return {
        "unit_price": item.unit_price,
        "date": item.invoice.invoice_date,
        "invoice_number": item.invoice.number,
    }


def last_completed_purchase_rates_bulk(
    company, pairs, *, exclude_invoice_id=None
) -> dict[tuple[int, int], dict]:
    """Batch form of ``last_completed_purchase_rate`` — one query for many
    (supplier_id, product_id) pairs instead of one query per pair.

    Exists so a serializer rendering N line items on one invoice doesn't
    issue N queries for the price-jump note (each call to
    ``last_completed_purchase_rate`` hits the DB once). Returns the same
    per-pair shape, keyed by ``(supplier_id, product_id)``; a pair with no
    prior completed purchase is simply absent from the result, matching
    ``last_completed_purchase_rate``'s ``None`` return for that case.
    """
    from purchases.models import PurchaseInvoice, PurchaseItem

    wanted = {(s, p) for s, p in pairs if s is not None and p is not None}
    if not wanted:
        return {}
    supplier_ids = {s for s, _ in wanted}
    product_ids = {p for _, p in wanted}
    qs = (
        PurchaseItem.objects.filter(
            company=company,
            product_id__in=product_ids,
            invoice__supplier_id__in=supplier_ids,
            invoice__status=PurchaseInvoice.Status.COMPLETED,
        )
        .select_related("invoice")
        .order_by("invoice__supplier_id", "product_id", "-invoice__invoice_date", "-id")
    )
    if exclude_invoice_id:
        qs = qs.exclude(invoice_id=exclude_invoice_id)
    result: dict[tuple[int, int], dict] = {}
    for item in qs:
        key = (item.invoice.supplier_id, item.product_id)
        # Rows are ordered most-recent-first within each (supplier, product)
        # group, so the first row seen for a key is the one we want — skip
        # once it's already been recorded, and skip pairs nobody asked for.
        if key not in wanted or key in result:
            continue
        result[key] = {
            "unit_price": item.unit_price,
            "date": item.invoice.invoice_date,
            "invoice_number": item.invoice.number,
        }
    return result
