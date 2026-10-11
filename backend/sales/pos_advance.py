"""Apply a customer's unallocated advance to a counter bill."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from core.exceptions import BusinessRuleError

Q2 = Decimal("0.01")


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Q2, rounding=ROUND_HALF_UP)


def apply_customer_advance(invoice, amount, user) -> Decimal:
    """Allocate unallocated receipts onto this invoice, up to `amount` and the amount still open."""
    from ledgers.services import LedgerService
    from payments.models import CustomerReceipt, ReceiptStatus
    from payments.receipt_math import cash_available
    from payments.services import PaymentService

    requested = _money(amount)
    if requested <= 0:
        return Decimal("0.00")
    outstanding = _money(LedgerService.sales_invoice_outstanding(invoice))
    room = min(requested, outstanding)
    if room <= 0:
        return Decimal("0.00")

    applied = Decimal("0.00")
    receipts = CustomerReceipt.objects.filter(
        company=invoice.company,
        customer=invoice.customer,
        status=ReceiptStatus.POSTED,
    ).order_by("id")
    for receipt in receipts:
        if applied >= room:
            break
        free = _money(cash_available(receipt))
        if free <= 0:
            continue
        take = min(free, room - applied)
        PaymentService.allocate_receipt(
            receipt=receipt,
            sales_invoice=invoice,
            amount=take,
            user=user,
        )
        applied += take
    if applied <= 0 and requested > 0:
        raise BusinessRuleError(
            "This customer has no advance to apply.",
            code="pos_no_advance",
        )
    return applied.quantize(Q2, rounding=ROUND_HALF_UP)
