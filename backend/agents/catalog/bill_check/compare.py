"""Deterministic bill checks (plan AGT-501/502). Read-only: nothing here saves or blocks a bill.

``compare_bill`` uses the same tolerances as ``PurchaseService.match_bill_to_po`` and reports, per finding, a code,
a plain sentence made only of facts, and whether it is something to tell the supplier (``to_supplier``) or only
for the owner. The protection rules are the ones the data supports today: duplicate supplier bill number, amount
far above the supplier's usual bills, a supplier whose GSTIN is marked cancelled. (Supplier bank details and GSTIN
history are not stored per supplier, so "changed bank details" and "new GSTIN" cannot be checked yet.)
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

MIN_HISTORY = 6
HIGH_FACTOR = Decimal("1.0")  # strictly above the supplier's 95th-percentile bill


def _d(value) -> Decimal:
    return Decimal(str(value or 0))


def _q(value) -> str:
    return format(_d(value).quantize(Decimal("0.01")), "f")


def _qty(value) -> str:
    return format(_d(value).normalize(), "f")


def _finding(code, text, *, to_supplier, product_id=None, severity="warn") -> dict:
    return {"code": code, "text": text, "to_supplier": to_supplier, "product_id": product_id, "severity": severity}


def p95(values: list[Decimal]) -> Decimal:
    """Nearest-rank 95th percentile."""
    ordered = sorted(values)
    rank = max(1, -(-95 * len(ordered) // 100))
    return ordered[rank - 1]


def compare_bill(invoice) -> dict:
    """{findings, rows}. ``rows`` feed the side-by-side view: left is what we agreed or received, right is the bill."""
    from purchases.models import GoodsReceipt, PurchaseInvoice
    from purchases.services import _THREE_WAY_QTY_TOLERANCE, _three_way_rate_tolerance

    orders = list(invoice.source_orders.prefetch_related("items"))
    grns = list(
        invoice.source_grns.filter(status=GoodsReceipt.Status.COMPLETED)
        .select_related("purchase_order").prefetch_related("items", "purchase_order__items")
    )
    seen = {o.pk for o in orders}
    for grn in grns:
        po = grn.purchase_order
        if po is not None and po.pk not in seen:
            orders.append(po)
            seen.add(po.pk)

    findings: list[dict] = []
    rows: list[dict] = []

    po_qty, po_rates, po_gst = defaultdict(Decimal), defaultdict(list), {}
    for order in orders:
        for line in order.items.all():
            po_qty[line.product_id] += _d(line.quantity)
            po_rates[line.product_id].append(_d(line.unit_price).quantize(Decimal("0.01")))
            po_gst.setdefault(line.product_id, _d(line.gst_rate))
    grn_qty, grn_rates = defaultdict(Decimal), defaultdict(list)
    for grn in grns:
        for line in grn.items.all():
            grn_qty[line.product_id] += _d(line.quantity_accepted)
            price = _d(line.unit_price).quantize(Decimal("0.01"))
            if price > 0:
                grn_rates[line.product_id].append(price)

    lines = list(invoice.items.select_related("product"))
    bill_qty, names = defaultdict(Decimal), {}
    for item in lines:
        bill_qty[item.product_id] += _d(item.quantity)
        names[item.product_id] = item.product.name

    def outside(rate, agreed):
        return all(abs(rate - a) > _three_way_rate_tolerance(a) for a in agreed)

    for item in lines:
        pid, name = item.product_id, item.product.name
        rate = _d(item.unit_price).quantize(Decimal("0.01"))
        agreed = po_rates.get(pid) or grn_rates.get(pid)
        source = "PO" if pid in po_rates else "GRN"
        if agreed:
            bad = outside(rate, agreed)
            rows.append({"field": f"{name}: rate", "left": _q(agreed[-1]), "right": _q(rate), "mismatch": bad})
            if bad:
                findings.append(_finding(
                    "RATE_DIFF", f"{name}: the bill rate is {_q(rate)} but the {source} rate is {_q(agreed[-1])}.",
                    to_supplier=True, product_id=pid))
        if orders and pid not in po_rates:
            findings.append(_finding("NOT_ON_PO", f"{name} is on the bill but not on the purchase order.", to_supplier=True, product_id=pid))
        if pid in po_gst and _d(item.gst_rate) != po_gst[pid]:
            rows.append({"field": f"{name}: GST %", "left": _qty(po_gst[pid]), "right": _qty(item.gst_rate), "mismatch": True})
            findings.append(_finding(
                "GST_RATE_DIFF", f"{name}: the bill shows GST {_qty(item.gst_rate)}% but the purchase order shows {_qty(po_gst[pid])}%.",
                to_supplier=True, product_id=pid))

    for pid, qty in bill_qty.items():
        name = names[pid]
        if grns:
            accepted = grn_qty.get(pid, Decimal("0"))
            bad = abs(qty - accepted) > _THREE_WAY_QTY_TOLERANCE
            rows.append({"field": f"{name}: quantity", "left": _qty(accepted), "right": _qty(qty), "mismatch": bad})
            if bad:
                findings.append(_finding(
                    "QTY_VS_GRN", f"{name}: the bill has {_qty(qty)} but we received and accepted {_qty(accepted)}.",
                    to_supplier=True, product_id=pid))
        elif orders:
            ordered = po_qty.get(pid, Decimal("0"))
            bad = qty - ordered > _THREE_WAY_QTY_TOLERANCE
            rows.append({"field": f"{name}: quantity", "left": _qty(ordered), "right": _qty(qty), "mismatch": bad})
            if bad:
                findings.append(_finding(
                    "QTY_OVER_PO", f"{name}: the bill has {_qty(qty)} but the purchase order has {_qty(ordered)}.",
                    to_supplier=True, product_id=pid))
    for pid, accepted in grn_qty.items():
        if accepted > 0 and pid not in bill_qty:
            findings.append(_finding("GRN_NOT_BILLED", f"We received {_qty(accepted)} of an item that is missing on the bill.", to_supplier=True, product_id=pid))
    if orders and not grns and any(line.product.track_inventory for line in lines):
        findings.append(_finding("NO_GRN", "No goods receipt is recorded against this bill yet.", to_supplier=False))

    # Protection rules.
    number = (invoice.supplier_bill_number or "").strip()
    if number and PurchaseInvoice.objects.filter(
        company=invoice.company, supplier_id=invoice.supplier_id, supplier_bill_number__iexact=number,
    ).exclude(pk=invoice.pk).exclude(status=PurchaseInvoice.Status.CANCELLED).exists():
        findings.append(_finding("DUPLICATE_BILL_NO", f"Bill number {number} was already booked for this supplier.", to_supplier=True, severity="block"))
    history = [
        _d(v) for v in PurchaseInvoice.objects.filter(
            company=invoice.company, supplier_id=invoice.supplier_id, status=PurchaseInvoice.Status.COMPLETED,
        ).exclude(pk=invoice.pk).order_by("-invoice_date", "-id").values_list("grand_total", flat=True)[:200]
    ]
    if len(history) >= MIN_HISTORY and _d(invoice.grand_total) > p95(history) * HIGH_FACTOR:
        findings.append(_finding(
            "AMOUNT_HIGH", f"This bill is {_q(invoice.grand_total)}, higher than the supplier's usual range (95% of earlier bills are up to {_q(p95(history))}).",
            to_supplier=False))
    if getattr(invoice.supplier, "gstin_cancelled_on", None):
        findings.append(_finding("GSTIN_CANCELLED", "The supplier's GSTIN is marked cancelled in our records.", to_supplier=False, severity="block"))
    return {"findings": findings, "rows": rows}
