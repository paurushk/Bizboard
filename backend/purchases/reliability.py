"""Lead time and fill rate. Two numbers, no score and no rank."""

from __future__ import annotations

from decimal import Decimal

from purchases.models import GoodsReceipt, PurchaseOrder, PurchaseOrderItem


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

    ordered = Decimal("0")
    received = Decimal("0")
    lines = PurchaseOrderItem.objects.filter(
        company=company,
        product=product,
        purchase_order__supplier=supplier,
    ).exclude(purchase_order__status=PurchaseOrder.Status.CANCELLED)
    for line in lines:
        ordered += Decimal(str(line.quantity or 0))
    receipt_items = []
    for receipt in receipts:
        receipt_items.extend(
            receipt.items.filter(product=product)
        )
    for item in receipt_items:
        received += Decimal(str(item.quantity_received or 0))
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
