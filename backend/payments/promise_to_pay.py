"""Promise-to-pay: a customer's stated commitment to pay by a given date.

Deliberately small — create / list-open / mark-resolved plus a "due today"
query that a digest or the Attention feed can consume later. No new
prediction mechanism, no auto-anything: this is a human-entered note against
a customer (optionally against one invoice).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from core.services.audit import AuditService

from .models import CustomerReceipt, PaymentPromise, ReceiptStatus


def create_promise(
    *,
    company,
    customer,
    invoice=None,
    promised_date: date,
    note: str = "",
    user=None,
    promised_amount=None,
) -> PaymentPromise:
    amount = None
    if promised_amount is not None and promised_amount != "":
        amount = Decimal(str(promised_amount)).quantize(Decimal("0.01"))
        if amount <= 0:
            amount = None
    promise = PaymentPromise.objects.create(
        company=company,
        customer=customer,
        invoice=invoice,
        promised_date=promised_date,
        promised_amount=amount,
        note=note or "",
        created_by=user,
        updated_by=user,
    )
    AuditService.log(
        company=company,
        user=user,
        action="CREATE",
        entity_type="PaymentPromise",
        entity_id=promise.pk,
        description=f"Promise to pay by {promised_date.isoformat()} for {customer.name}",
    )
    return promise


def list_open_promises(company, *, customer=None):
    """Unresolved promises for a company, newest first. Optionally scoped to one customer."""
    qs = PaymentPromise.objects.filter(company=company, resolved=False)
    if customer is not None:
        qs = qs.filter(customer=customer)
    return qs.select_related("customer", "invoice").order_by("promised_date", "id")


def resolve_promise(promise: PaymentPromise, *, user=None) -> PaymentPromise:
    """Mark a promise resolved (paid, or explicitly dismissed) — idempotent."""
    if not promise.resolved:
        promise.resolved = True
        promise.resolved_at = timezone.now()
        promise.updated_by = user
        promise.save(update_fields=["resolved", "resolved_at", "updated_by", "updated_at"])
        AuditService.log(
            company=promise.company,
            user=user,
            action="UPDATE",
            entity_type="PaymentPromise",
            entity_id=promise.pk,
            description="Promise to pay resolved",
        )
    return promise


def promise_amount_label(promise: PaymentPromise) -> str:
    if promise.promised_amount is None:
        return "amount not recorded"
    return str(promise.promised_amount)


def promise_is_broken(promise: PaymentPromise, *, as_of: date | None = None) -> bool:
    """Past-due, still open, and receipts since the promise do not cover it.

    A promise with no stored amount is not broken and is not ₹0.
    """
    if promise.promised_amount is None or promise.resolved:
        return False
    today = as_of or timezone.localdate()
    if promise.promised_date >= today:
        return False
    since = (
        timezone.localtime(promise.created_at).date()
        if promise.created_at
        else promise.promised_date
    )
    receipts = CustomerReceipt.objects.filter(
        company_id=promise.company_id,
        customer_id=promise.customer_id,
        status=ReceiptStatus.POSTED,
        receipt_date__gte=since,
    )
    if promise.invoice_id:
        from payments.models import PaymentAllocation

        received = PaymentAllocation.objects.filter(
            receipt__in=receipts,
            sales_invoice_id=promise.invoice_id,
            reversed_at__isnull=True,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    else:
        received = receipts.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return Decimal(str(received)) < promise.promised_amount


def received_since_promise(promise: PaymentPromise) -> Decimal:
    """What the customer has paid since the promise was made, against it (one invoice or any)."""
    since = (
        timezone.localtime(promise.created_at).date()
        if promise.created_at
        else promise.promised_date
    )
    receipts = CustomerReceipt.objects.filter(
        company_id=promise.company_id,
        customer_id=promise.customer_id,
        status=ReceiptStatus.POSTED,
        receipt_date__gte=since,
    )
    if getattr(promise.company, "cheque_allocation_on_clearance", False):
        # This company does not count a cheque as received until it clears.
        from payments.models import ChequeStatus, PaymentMode

        receipts = receipts.exclude(
            mode=PaymentMode.CHEQUE, cheque_status=ChequeStatus.PENDING_CLEARANCE
        )
    if promise.invoice_id:
        from payments.models import PaymentAllocation

        total = PaymentAllocation.objects.filter(
            receipt__in=receipts, sales_invoice_id=promise.invoice_id, reversed_at__isnull=True,
        ).aggregate(total=Sum("amount"))["total"]
    else:
        total = receipts.aggregate(total=Sum("amount"))["total"]
    return Decimal(str(total or 0))


def promise_is_kept(promise: PaymentPromise) -> bool:
    """Open, has an amount, and receipts since it was made cover that amount."""
    if promise.resolved or promise.promised_amount is None:
        return False
    return received_since_promise(promise) >= promise.promised_amount


def close_kept_promises(company, customer, *, receipt=None, user=None) -> int:
    """Close every open promise of this customer that the money received now covers."""
    closed = 0
    for promise in PaymentPromise.objects.filter(company=company, customer=customer, resolved=False):
        if promise_is_kept(promise):
            promise.auto_resolved_by_receipt = receipt
            promise.save(update_fields=["auto_resolved_by_receipt", "updated_at"])
            resolve_promise(promise, user=user)
            closed += 1
    return closed


def reopen_unkept_promises(receipt, *, user=None) -> int:
    """A void took money back: reopen the promises this receipt had closed, unless covered still."""
    reopened = 0
    for promise in PaymentPromise.objects.filter(auto_resolved_by_receipt=receipt, resolved=True):
        promise.resolved = False
        promise.resolved_at = None
        promise.auto_resolved_by_receipt = None
        promise.updated_by = user
        promise.save(update_fields=[
            "resolved", "resolved_at", "auto_resolved_by_receipt", "updated_by", "updated_at",
        ])
        if promise_is_kept(promise):
            # Another receipt still covers it.
            resolve_promise(promise, user=user)
        else:
            reopened += 1
            AuditService.log(
                company=promise.company, user=user, action="UPDATE", entity_type="PaymentPromise",
                entity_id=promise.pk, description="Promise to pay reopened: its receipt was voided",
            )
    return reopened


def broken_promise_total(company, *, as_of: date | None = None) -> Decimal:
    today = as_of or timezone.localdate()
    total = Decimal("0")
    rows = PaymentPromise.objects.filter(
        company=company,
        resolved=False,
        promised_date__lt=today,
        promised_amount__isnull=False,
    )
    for promise in rows:
        if promise_is_broken(promise, as_of=today):
            total += promise.promised_amount
    return total


def promises_due_today(company, *, as_of: date | None = None):
    """Unresolved promises whose promised_date is today, company-local time.

    Consumable by the Attention feed / a daily digest — see
    ``insights.attention``'s builder-function pattern for a possible
    ``_promise_to_pay`` builder (not wired in from here; this is the query
    such a builder would call).
    """
    today = as_of or timezone.localdate()
    return (
        PaymentPromise.objects.filter(company=company, resolved=False, promised_date=today)
        .select_related("customer", "invoice")
        .order_by("customer__name", "id")
    )
