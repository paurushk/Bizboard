"""Shareable quotation links (closure plan WP14b, decision D-19).

A link opens the quotation's PDF without signing in. It stops working when the
quotation is cancelled or rejected, when it goes back to DRAFT for edits, or when
its validity date passes.
"""

from __future__ import annotations

import secrets
from datetime import datetime, time, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.exceptions import BusinessRuleError

from .models import Quotation, QuotationPublicLink

# Quotes without a validity date still expire, so a forgotten link does not live forever.
DEFAULT_LINK_DAYS = 30
SHAREABLE_STATUSES = (
    Quotation.Status.DRAFT,
    Quotation.Status.SENT,
    Quotation.Status.ACCEPTED,
    Quotation.Status.CONVERTED,
)


def public_quotation_url(token: str) -> str:
    from payments.webhook_views import public_frontend_base_url

    return f"{public_frontend_base_url()}/q/{token}"


def _expiry_for(quotation) -> datetime:
    if quotation.valid_until:
        end = datetime.combine(quotation.valid_until, time.max)
        return timezone.make_aware(end) if timezone.is_naive(end) else end
    return timezone.now() + timedelta(days=DEFAULT_LINK_DAYS)


def active_link(quotation) -> QuotationPublicLink | None:
    row = (
        QuotationPublicLink.objects.filter(quotation=quotation, revoked_at__isnull=True)
        .order_by("-id")
        .first()
    )
    if row is None:
        return None
    if row.expires_at is not None and row.expires_at <= timezone.now():
        return None
    return row


def mint_link(quotation, user) -> QuotationPublicLink:
    if quotation.status not in SHAREABLE_STATUSES:
        raise BusinessRuleError(
            "A cancelled or rejected quotation cannot be shared.", code="quotation_not_shareable"
        )
    existing = active_link(quotation)
    if existing is not None:
        return existing
    # An expired, unrevoked row would block the one-active-link constraint.
    QuotationPublicLink.objects.filter(quotation=quotation, revoked_at__isnull=True).update(
        revoked_at=timezone.now()
    )
    try:
        with transaction.atomic():
            return QuotationPublicLink.objects.create(
                company=quotation.company,
                quotation=quotation,
                token=secrets.token_urlsafe(32),
                expires_at=_expiry_for(quotation),
                created_by=user,
                updated_by=user,
            )
    except IntegrityError:
        existing = active_link(quotation)
        if existing is not None:
            return existing
        raise


def revoke_links(quotation) -> int:
    return QuotationPublicLink.objects.filter(quotation=quotation, revoked_at__isnull=True).update(
        revoked_at=timezone.now()
    )
