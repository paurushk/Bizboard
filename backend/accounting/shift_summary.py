"""Z-report for one cash shift. Reads the same rows expected cash uses."""

from __future__ import annotations

import io
from decimal import Decimal

from django.db.models import Sum
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from payments.models import CustomerReceipt, PaymentMode, ReceiptStatus


def render_shift_summary(shift) -> bytes:
    from accounting.cash_shifts import expected_system_cash
    from accounting.models import CashDrop
    from sales.models import PosCounterRefund

    company = shift.company
    receipts = CustomerReceipt.objects.filter(company=company, shift=shift).exclude(
        status__in=(ReceiptStatus.VOIDED, ReceiptStatus.REFUNDED),
    )
    by_mode = {
        row["mode"]: row["total"]
        for row in receipts.values("mode").annotate(total=Sum("amount"))
    }
    refunds = PosCounterRefund.objects.filter(
        shift=shift, status=PosCounterRefund.Status.POSTED,
    ).exclude(mode=PosCounterRefund.Mode.ADVANCE)
    refund_total = refunds.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    drops = list(CashDrop.objects.filter(shift=shift).order_by("dropped_at"))
    expected = expected_system_cash(
        company, shift.cashier, shift.business_date, shift.opening_float,
        cash_dropped=shift.cash_dropped, shift=shift,
    )
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    y = 280 * mm
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(20 * mm, y, f"Shift summary {shift.business_date}")
    pdf.setFont("Helvetica", 10)
    lines = [
        f"Terminal: {shift.terminal_label or shift.terminal_id}",
        f"Opened: {shift.opened_at or ''}",
        f"Closed: {shift.closed_at or ''}",
        f"Opening float: {shift.opening_float}",
        f"Cash sales: {by_mode.get(PaymentMode.CASH, 0)}",
        f"UPI: {by_mode.get(PaymentMode.UPI, 0)}",
        f"Card: {by_mode.get(PaymentMode.CARD, 0)}",
        f"Bank: {by_mode.get(PaymentMode.BANK, 0)}",
        f"Cheque: {by_mode.get(PaymentMode.CHEQUE, 0)}",
        f"Refunds: {refund_total}",
        f"Drops: {sum((row.amount for row in drops), Decimal('0'))}",
        f"Expected cash: {expected}",
        f"Counted: {shift.counted_cash}",
        f"Variance: {shift.variance}",
    ]
    for line in lines:
        y -= 7 * mm
        pdf.drawString(20 * mm, y, line)
    pdf.showPage()
    pdf.save()
    return buf.getvalue()
