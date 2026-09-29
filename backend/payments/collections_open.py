"""Open sales invoices for the collections screen.

The row balance is one invoice's outstanding. The customer total, when shown,
is the party balance and is a different number.
"""

from __future__ import annotations

from decimal import Decimal
from urllib.parse import quote

from django.db.models import Sum
from django.utils import timezone

from ledgers.services import LedgerService
from payments.models import PaymentAllocation
from sales.models import SalesInvoice
from sales.status_semantics import OPEN_SALES_STATUSES


def _wa_digits(phone: str) -> str:
    """Digits for a wa.me link. Indian numbers only; anything else gets no direct link.

    Accepts 9876543210, 09876543210, +91 98765 43210, 919876543210.
    """
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"91{digits}"
    if len(digits) == 12 and digits.startswith("91"):
        return digits
    return ""


def open_invoice_rows(company, as_of=None) -> list[dict]:
    as_of = as_of or timezone.localdate()
    invoices = list(
        SalesInvoice.objects.filter(company=company, status__in=OPEN_SALES_STATUSES)
        .select_related("customer")
        .order_by("due_date", "id")
    )
    if not invoices:
        return []
    ids = [invoice.id for invoice in invoices]
    outstanding = LedgerService.bulk_sales_invoice_outstanding(company, ids)
    received = dict(
        PaymentAllocation.objects.filter(
            sales_invoice_id__in=ids,
            receipt__isnull=False,
            supplier_payment__isnull=True,
            reversed_at__isnull=True,
        )
        .values("sales_invoice_id")
        .annotate(total=Sum("amount"))
        .values_list("sales_invoice_id", "total")
    )
    party = LedgerService.bulk_customer_outstanding(company)
    rows = []
    for invoice in invoices:
        owed = outstanding.get(invoice.id) or Decimal("0")
        if owed <= 0:
            continue
        due = invoice.due_date or invoice.invoice_date
        days_overdue = (as_of - due).days if due and due < as_of else 0
        phone = (getattr(invoice.customer, "phone", "") or "").strip()
        digits = _wa_digits(phone)
        message = (
            f"Reminder: invoice {invoice.number or invoice.id} has "
            f"₹{owed} outstanding. Please pay at your earliest."
        )
        rows.append({
            "invoice_id": invoice.id,
            "invoice_number": invoice.number,
            "customer_id": invoice.customer_id,
            "customer_name": invoice.customer.name,
            "customer_phone": phone,
            "remind_message": message,
            "remind_url": (
                f"https://wa.me/{digits}?text={quote(message)}"
                if digits
                else f"https://wa.me/?text={quote(message)}"
            ),
            "due_date": due.isoformat() if due else None,
            "days_overdue": days_overdue,
            "amount_received": str(received.get(invoice.id) or Decimal("0")),
            "outstanding": str(owed),
            "customer_outstanding": str(party.get(invoice.customer_id) or Decimal("0")),
        })
    return rows
