"""What an office user needs to know about a stop beyond its address (hardening plan R5).

Read-only. A stop carries an order; the order may have a challan, one or several invoices, and a
customer who may owe money or hold an advance. This turns that into the few facts a dispatcher or
cashier acts on: what is on the bill, what the driver should collect, whether it is already paid.

Customer money position (an advance on account) follows the Customer 360 rule
(``insights.customer_360.can_open_customer_360``); the bill itself is a sales document, so anyone
who can see the route sees it.
"""

from __future__ import annotations

from decimal import Decimal

_ZERO = Decimal("0")


def _money(value) -> str:
    return str(Decimal(str(value or 0)).quantize(Decimal("0.01")))


def stop_bill_info(stop, *, include_customer_money: bool = False) -> dict:
    """The bill, the payment terms and the amount to collect for one stop."""
    from ledgers.services import LedgerService

    from .models import DeliveryChallan, SalesInvoice
    from .order_quantities import invoices_for_order, live_challans_for_order

    order = stop.sales_order
    invoices = list(invoices_for_order(order).order_by("id"))
    completed = [
        inv for inv in invoices if inv.status in (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED)
    ]
    rows = []
    owed = _ZERO
    for inv in invoices:
        balance = _ZERO
        if inv in completed:
            balance = Decimal(str(LedgerService.sales_invoice_outstanding(inv) or 0))
            owed += balance
        rows.append({
            "id": inv.pk,
            "number": inv.number or "",
            "status": inv.status,
            "grand_total": _money(inv.grand_total),
            "balance": _money(balance),
        })
    challans = list(live_challans_for_order(order).filter(status=DeliveryChallan.Status.COMPLETED))

    if completed:
        bill_status = "paid" if owed <= 0 else "invoiced"
        due = owed
    elif invoices:
        bill_status = "draft_invoice"
        due = Decimal(str(order.grand_total or 0))
    elif challans:
        bill_status = "challan"
        due = Decimal(str(order.grand_total or 0))
    else:
        bill_status = "order_only"
        due = Decimal(str(order.grand_total or 0))

    terms = int(order.payment_terms_days or 0)
    # A credit sale is paid later, not at the door; a cash sale is collected on delivery.
    to_collect = _ZERO if terms > 0 else (due if due > 0 else _ZERO)
    info = {
        "order_total": _money(order.grand_total),
        "payment_terms_days": terms,
        "bill_status": bill_status,
        "invoices": rows,
        "amount_to_collect": _money(to_collect),
        "on_credit": terms > 0,
    }
    if include_customer_money:
        info["advance_available"] = _money(
            LedgerService.customer_unallocated_receipts(order.company, order.customer)
        )
    return info
