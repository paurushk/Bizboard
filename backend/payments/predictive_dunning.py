"""Predictive days-late. Screen only — the existing reminder cadence still sends."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from statistics import median

from django.utils import timezone

from payments.models import PaymentAllocation, ReceiptStatus

CONFIDENT_MIN_INVOICES = 3
RECENT_INVOICES = 5
APPEAR_DAYS_BEFORE = 3
MIN_PREDICTED_LATE_DAYS = 2


def _due(invoice):
    if invoice.due_date:
        return invoice.due_date
    return invoice.invoice_date + timedelta(days=invoice.payment_terms_days or 0)


def median_days_late(company, customer) -> int | None:
    """Median days late over the last 5 paid invoices. None below 3 samples."""
    allocations = (
        PaymentAllocation.objects.filter(
            company=company,
            sales_invoice__customer=customer,
            sales_invoice__isnull=False,
            receipt__isnull=False,
            reversed_at__isnull=True,
            receipt__status=ReceiptStatus.POSTED,
        )
        .select_related("sales_invoice", "receipt")
        .order_by("-receipt__receipt_date", "-id")
    )
    seen = []
    seen_ids = set()
    for row in allocations:
        invoice = row.sales_invoice
        if invoice.id in seen_ids:
            continue
        seen_ids.add(invoice.id)
        paid_on = row.receipt.receipt_date
        late = (paid_on - _due(invoice)).days
        seen.append(late)
        if len(seen) >= RECENT_INVOICES:
            break
    if len(seen) < CONFIDENT_MIN_INVOICES:
        return None
    return int(median(seen))


def _window_invoices(company, as_of):
    """Open invoices whose due date can fall in the next few days. Not the whole book."""
    from django.db.models import Q

    from sales.models import SalesInvoice
    from sales.status_semantics import OPEN_RECEIVABLE_STATUSES

    horizon = as_of + timedelta(days=APPEAR_DAYS_BEFORE)
    lookback = as_of - timedelta(days=120)
    return SalesInvoice.objects.filter(
        company=company,
        status__in=OPEN_RECEIVABLE_STATUSES,
        is_opening_balance=False,
    ).filter(
        Q(due_date__gte=as_of, due_date__lte=horizon)
        | Q(due_date__isnull=True, invoice_date__gte=lookback, invoice_date__lte=horizon)
    ).select_related("customer")


def _late_enough(company, invoice, patterns) -> int | None:
    customer = invoice.customer
    if customer.id not in patterns:
        patterns[customer.id] = median_days_late(company, customer)
    late = patterns[customer.id]
    if late is None or late < MIN_PREDICTED_LATE_DAYS:
        return None
    return late


def predicted_rows(company, as_of=None) -> list[dict]:
    """Attention-shaped dicts for invoices due within 3 days when lateness is 2+ days."""
    from core.services.feature_flags import flag_enabled
    from ledgers.services import LedgerService

    if not flag_enabled(company, "ENABLE_PREDICTIVE_DUNNING"):
        return []
    as_of = as_of or timezone.localdate()
    horizon = as_of + timedelta(days=APPEAR_DAYS_BEFORE)
    invoices = list(_window_invoices(company, as_of))
    outstanding = LedgerService.bulk_sales_invoice_outstanding(
        company, invoice_ids=[invoice.id for invoice in invoices]
    )
    patterns: dict[int, int | None] = {}
    rows = []
    for invoice in invoices:
        due = _due(invoice)
        if due < as_of or due > horizon:
            continue
        owed = outstanding.get(invoice.id) or Decimal("0")
        if owed <= 0:
            continue
        late = _late_enough(company, invoice, patterns)
        if late is None:
            continue
        customer = invoice.customer
        paise = int((owed * 100).to_integral_value())
        rows.append({
            "code": "PREDICTED_LATE_PAYMENT",
            "severity": "warning",
            "title": f"{customer.name} usually pays {late} days late",
            "money_impact_paise": paise,
            "currency": "INR",
            "reason": (
                f"₹{owed} is due {due.isoformat()}. "
                f"The last paid invoices point to about {late} days late."
            ),
            "action_label": "Open collections",
            "action_href": "/payments/collections",
            "source_ticket": "B2",
            "entity_ref": {"type": "customer", "id": int(customer.id)},
            "dedupe_key": f"PREDICTED_LATE_PAYMENT:{invoice.id}",
            "first_seen": None,
            "snooze_until": None,
        })
    return rows


def collections_worklist(company, as_of=None) -> list[dict]:
    """The same predicted-late invoices as Today. Cold starts stay off this list."""
    from core.services.feature_flags import flag_enabled
    from ledgers.services import LedgerService

    if not flag_enabled(company, "ENABLE_PREDICTIVE_DUNNING"):
        return []
    as_of = as_of or timezone.localdate()
    horizon = as_of + timedelta(days=APPEAR_DAYS_BEFORE)
    invoices = list(_window_invoices(company, as_of))
    outstanding = LedgerService.bulk_sales_invoice_outstanding(
        company, invoice_ids=[inv.id for inv in invoices]
    )
    patterns: dict[int, int | None] = {}
    rows = []
    for invoice in invoices:
        due = _due(invoice)
        if due < as_of or due > horizon:
            continue
        owed = outstanding.get(invoice.id) or Decimal("0")
        if owed <= 0:
            continue
        late = _late_enough(company, invoice, patterns)
        if late is None:
            continue
        customer = invoice.customer
        rows.append({
            "invoice_id": invoice.id,
            "invoice_number": invoice.number,
            "customer_id": customer.id,
            "customer_name": customer.name,
            "due_date": due.isoformat(),
            "outstanding": str(owed),
            "predicted_days_late": late,
            "confident": True,
        })
    rows.sort(
        key=lambda row: (
            -(row["predicted_days_late"] or -1),
            row["due_date"],
            row["invoice_id"],
        )
    )
    return rows
