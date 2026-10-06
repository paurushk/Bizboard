"""GST invoice from Bizboard to a tenant. No gateway SDK."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.utils import timezone

from core.models import Notification
from core.services.notifications import NotificationService

from .models import PlatformGstInvoice

_PROVIDERS = {"cashfree", "payu"}
_RATE = Decimal("1.18")


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def issue_platform_gst_invoice(company, *, provider: str, capture_id: str, amount, user=None):
    """One invoice per capture. A second delivery returns the same row."""
    provider = (provider or "").strip().lower()
    if provider not in _PROVIDERS or not capture_id:
        return None
    existing = PlatformGstInvoice.objects.filter(
        company=company, provider=provider, capture_id=capture_id,
    ).first()
    if existing is not None:
        return existing
    total = _money(Decimal(str(amount)))
    taxable = _money(total / _RATE)
    tax = _money(total - taxable)
    platform_state = (getattr(settings, "PLATFORM_STATE", "") or "").strip()
    tenant_state = (getattr(company, "state", "") or "").strip()
    same_state = bool(platform_state and tenant_state and platform_state.casefold() == tenant_state.casefold())
    half = _money(tax / 2) if same_state else Decimal("0.00")
    row = PlatformGstInvoice.objects.create(
        company=company,
        provider=provider,
        capture_id=capture_id,
        number=f"PLT-{company.pk}-{capture_id[:12]}",
        taxable_amount=taxable,
        cgst=half,
        sgst=_money(tax - half) if same_state else Decimal("0.00"),
        igst=Decimal("0.00") if same_state else tax,
        total=total,
        place_of_supply=tenant_state,
        platform_gstin=(getattr(settings, "PLATFORM_GSTIN", "") or "")[:15],
        created_by=user if getattr(user, "pk", None) else None,
    )
    recipient = getattr(company, "email", "") or ""
    body = (
        f"GST invoice {row.number} for {row.total}. "
        f"Place of supply: {row.place_of_supply or 'not set'}. "
        f"Taxable {row.taxable_amount}, CGST {row.cgst}, SGST {row.sgst}, IGST {row.igst}."
    )
    if recipient:
        NotificationService.send(
            company=company, channel=Notification.Channel.EMAIL, recipient=recipient,
            subject=f"GST invoice {row.number}", body=body, user=user,
        )
    NotificationService.send(
        company=company, channel=Notification.Channel.IN_APP, recipient=recipient or str(company.pk),
        subject=f"GST invoice {row.number}", body=body, user=user,
    )
    row.emailed_at = timezone.now()
    row.save(update_fields=["emailed_at", "updated_at"])
    return row
