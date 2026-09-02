"""W0-03: verified gateway captures that cannot post books.

Park as CAPTURED_PENDING_BOOKS. Never drop a signed capture. Razorpay only.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from core.help_codes import HelpCode

from .models import GatewayPayment, GatewayPaymentStatus, PaymentLink, PaymentLinkStatus

PAYMENT_STATE_UNPAID = "UNPAID"
PAYMENT_STATE_PAID_PENDING_BOOKS = "PAID_PENDING_BOOKS"
PAYMENT_STATE_PAID = "PAID"

HOLDING_STATUSES = (GatewayPaymentStatus.CAPTURED_PENDING_BOOKS,)
CAPTURED_LIKE = (
    GatewayPaymentStatus.CAPTURED,
    GatewayPaymentStatus.CAPTURED_PENDING_BOOKS,
)


def gateway_holding_enabled() -> bool:
    return bool(getattr(settings, "GATEWAY_HOLDING_STATE", True))


def err_detail(exc) -> str:
    detail = getattr(exc, "detail", None)
    if detail is None:
        return str(exc)
    return str(detail)[:2000]


def books_hold_reason(exc) -> str:
    codes = ""
    getter = getattr(exc, "get_codes", None)
    if callable(getter):
        try:
            codes = str(getter())
        except Exception:
            codes = ""
    text = f"{codes} {err_detail(exc)}".lower()
    if HelpCode.CLOSED_PERIOD in text or "gst period" in text or "accounting period" in text:
        return "PERIOD_LOCKED"
    if "utr" in text and (
        "already used" in text
        or "duplicate" in text
        or "clash" in text
        or "customer differs" in text
        or "amount differs" in text
    ):
        return "UTR_CLASH"
    return "BOOKS_ERROR"


def park_gateway_payment(gp: GatewayPayment, reason: str, error: str = "") -> GatewayPayment:
    gp.status = GatewayPaymentStatus.CAPTURED_PENDING_BOOKS
    gp.holding_reason = (reason or "BOOKS_ERROR")[:64]
    gp.holding_error = (error or "")[:2000]
    if gp.holding_since is None:
        gp.holding_since = timezone.now()
    gp.save(
        update_fields=[
            "status",
            "holding_reason",
            "holding_error",
            "holding_since",
            "updated_at",
        ]
    )
    return gp


def clear_holding(gp: GatewayPayment) -> None:
    gp.holding_reason = ""
    gp.holding_error = ""
    gp.holding_since = None
    gp.status = GatewayPaymentStatus.CAPTURED
    gp.save(
        update_fields=[
            "status",
            "holding_reason",
            "holding_error",
            "holding_since",
            "updated_at",
        ]
    )


def suffixed_internal_utr(provider_payment_id: str, gp_pk: int) -> str:
    suffix = f"#G{gp_pk}"
    base = (provider_payment_id or "")[: max(1, 64 - len(suffix))]
    return f"{base}{suffix}"


def link_shows_paid(link: PaymentLink) -> bool:
    if link.status == PaymentLinkStatus.PAID:
        return True
    return GatewayPayment.objects.filter(payment_link=link, status__in=CAPTURED_LIKE).exists()


def invoice_payment_state(invoice) -> str:
    from ledgers.services import LedgerService

    outstanding = Decimal(str(LedgerService.sales_invoice_outstanding(invoice) or 0))
    if outstanding <= 0:
        return PAYMENT_STATE_PAID
    holding = GatewayPayment.objects.filter(
        payment_link__sales_invoice=invoice,
        status=GatewayPaymentStatus.CAPTURED_PENDING_BOOKS,
    ).exists()
    if holding:
        return PAYMENT_STATE_PAID_PENDING_BOOKS
    captured = GatewayPayment.objects.filter(
        payment_link__sales_invoice=invoice,
        status=GatewayPaymentStatus.CAPTURED,
    ).exists()
    if captured:
        return PAYMENT_STATE_PAID_PENDING_BOOKS if outstanding > 0 else PAYMENT_STATE_PAID
    return PAYMENT_STATE_UNPAID


def link_payment_state(link: PaymentLink) -> str:
    if link.sales_invoice_id:
        return invoice_payment_state(link.sales_invoice)
    if link_shows_paid(link):
        if GatewayPayment.objects.filter(
            payment_link=link,
            status=GatewayPaymentStatus.CAPTURED_PENDING_BOOKS,
        ).exists() and not GatewayPayment.objects.filter(
            payment_link=link,
            status=GatewayPaymentStatus.CAPTURED,
        ).exists():
            return PAYMENT_STATE_PAID_PENDING_BOOKS
        if link.status == PaymentLinkStatus.PAID:
            return PAYMENT_STATE_PAID
        return PAYMENT_STATE_PAID_PENDING_BOOKS
    return PAYMENT_STATE_UNPAID
