"""Shareable invoice links. A rolled-back or revoked token must not stay live."""

from __future__ import annotations

import secrets

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.help_codes import HelpCode

from .models import InvoicePublicLink, SalesInvoice


def public_invoice_url(token: str) -> str:
    from payments.webhook_views import public_frontend_base_url

    return f"{public_frontend_base_url()}/i/{token}"


def active_public_link(invoice) -> InvoicePublicLink | None:
    row = (
        InvoicePublicLink.objects.filter(invoice=invoice, revoked_at__isnull=True)
        .order_by("-id")
        .first()
    )
    if row is None:
        return None
    if row.expires_at is not None and row.expires_at <= timezone.now():
        return None
    return row


def mint_public_link(invoice, user) -> InvoicePublicLink:
    if invoice.status not in (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED):
        raise BusinessRuleError(
            "Only completed invoices can be shared.",
            code=HelpCode.PDF_OR_SHARE_UNAVAILABLE,
        )
    existing = active_public_link(invoice)
    if existing is not None:
        return existing
    try:
        with transaction.atomic():
            return InvoicePublicLink.objects.create(
                company=invoice.company,
                invoice=invoice,
                token=secrets.token_urlsafe(32),
                created_by=user,
                updated_by=user,
            )
    except IntegrityError:
        existing = active_public_link(invoice)
        if existing is not None:
            return existing
        raise


def revoke_invoice_public_links(invoice) -> None:
    InvoicePublicLink.objects.filter(invoice=invoice, revoked_at__isnull=True).update(
        revoked_at=timezone.now(),
    )
