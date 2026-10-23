"""GST invoice (and credit note) from Bizboard to a tenant. No gateway SDK.

WP-BL2: a Razorpay subscription charge (``subscription.charged``, or the daily recon for one a lost
webhook missed) issues the invoice; a refund issues a credit note against it. Amounts are GST
inclusive. Numbers are Bizboard-wide and gap-free per financial year (``BB2627-000001`` for
invoices, ``BC2627-000001`` for credit notes), within GST's 16-character limit.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.models import Notification
from core.services.notifications import NotificationService

from .models import PlatformGstInvoice, PlatformInvoiceSequence

_PROVIDERS = {"cashfree", "payu", "razorpay"}
_RATE = Decimal("1.18")
_PREFIX = {PlatformGstInvoice.Kind.INVOICE: "BB", PlatformGstInvoice.Kind.CREDIT_NOTE: "BC"}


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def financial_year(day=None) -> str:
    """Indian FY label for ``day``: April to March, e.g. ``2026-27``."""
    day = day or timezone.localdate()
    start = day.year if day.month >= 4 else day.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _next_number(kind: str, fy: str) -> str:
    """Take the next number in this kind's FY series. Call inside ``transaction.atomic``."""
    series = f"{'INV' if kind == PlatformGstInvoice.Kind.INVOICE else 'CRN'}:{fy}"
    try:
        with transaction.atomic():
            PlatformInvoiceSequence.objects.get_or_create(series=series)
    except IntegrityError:
        pass  # another worker created it a moment ago
    seq = PlatformInvoiceSequence.objects.select_for_update().get(series=series)
    seq.last += 1
    seq.save(update_fields=["last"])
    short_fy = fy[2:4] + fy[-2:]  # 2026-27 -> 2627
    return f"{_PREFIX[kind]}{short_fy}-{seq.last:06d}"


def _tax_split(company, total: Decimal) -> dict:
    """Split a GST-inclusive total. Intra-state is decided on GST state codes (the GSTINs' first two
    digits, else the state names), not raw strings; CGST and SGST are equal halves, with the paisa of
    rounding absorbed in the taxable value so the parts still add up to the total."""
    from core.services.tax_engine.india import is_intra_state

    platform_state = (getattr(settings, "PLATFORM_STATE", "") or "").strip()
    tenant_state = (getattr(company, "state", "") or "").strip()
    same_state = bool(platform_state or getattr(settings, "PLATFORM_GSTIN", "")) and is_intra_state(
        platform_state, tenant_state,
        company_gstin=(getattr(settings, "PLATFORM_GSTIN", "") or "").strip(),
        party_gstin=(getattr(company, "gstin", "") or "").strip(),
    )
    taxable = _money(total / _RATE)
    tax = _money(total - taxable)
    if same_state:
        half = _money(tax / 2)
        taxable = total - half - half
        return {
            "taxable_amount": taxable, "cgst": half, "sgst": half, "igst": Decimal("0.00"),
            "total": total, "place_of_supply": tenant_state,
        }
    return {
        "taxable_amount": taxable,
        "cgst": Decimal("0.00"),
        "sgst": Decimal("0.00"),
        "igst": tax,
        "total": total,
        "place_of_supply": tenant_state,
    }


def _buyer(company) -> dict:
    gstin = (getattr(company, "gstin", "") or "").strip().upper()
    legal = (getattr(company, "gstin_legal_name", "") or "").strip() if gstin else ""
    return {
        "buyer_gstin": gstin[:15],
        "buyer_legal_name": (legal or getattr(company, "name", "") or "")[:255],
        "buyer_state": (getattr(company, "state", "") or "").strip()[:64],
    }


def _issue(company, *, kind, provider, capture_id, amount, user=None, original=None):
    total = _money(Decimal(str(amount)))
    fy = financial_year()
    try:
        with transaction.atomic():
            row = PlatformGstInvoice.objects.create(
                company=company,
                provider=provider,
                capture_id=capture_id,
                kind=kind,
                original=original,
                number=_next_number(kind, fy),
                financial_year=fy,
                sac_code=(getattr(settings, "PLATFORM_SAC_CODE", "") or "998314")[:8],
                platform_gstin=(getattr(settings, "PLATFORM_GSTIN", "") or "")[:15],
                created_by=user if getattr(user, "pk", None) else None,
                **_buyer(company),
                **_tax_split(company, total),
            )
    except IntegrityError:
        # The same capture delivered twice at once: the number taken above rolled back with it.
        return PlatformGstInvoice.objects.get(company=company, provider=provider, capture_id=capture_id)
    _notify(company, row, user=user)
    return row


def _notify(company, row, *, user=None) -> None:
    label = "GST invoice" if row.kind == PlatformGstInvoice.Kind.INVOICE else "GST credit note"
    recipient = getattr(company, "email", "") or ""
    body = (
        f"{label} {row.number} for {row.total}. "
        f"Billed to: {row.buyer_legal_name}{' (GSTIN ' + row.buyer_gstin + ')' if row.buyer_gstin else ''}. "
        f"Place of supply: {row.place_of_supply or 'not set'}. SAC {row.sac_code}. "
        f"Taxable {row.taxable_amount}, CGST {row.cgst}, SGST {row.sgst}, IGST {row.igst}."
    )
    if recipient:
        NotificationService.send(
            company=company, channel=Notification.Channel.EMAIL, recipient=recipient,
            subject=f"{label} {row.number}", body=body, user=user,
        )
    NotificationService.send(
        company=company, channel=Notification.Channel.IN_APP, recipient=recipient or str(company.pk),
        subject=f"{label} {row.number}", body=body, user=user,
    )
    row.emailed_at = timezone.now()
    row.save(update_fields=["emailed_at", "updated_at"])


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
    return _issue(
        company, kind=PlatformGstInvoice.Kind.INVOICE, provider=provider, capture_id=capture_id,
        amount=amount, user=user,
    )


def issue_platform_credit_note(invoice: PlatformGstInvoice, *, refund_id: str, amount, user=None):
    """A credit note against ``invoice`` for a refund (GST inclusive). One per refund id."""
    if invoice.kind != PlatformGstInvoice.Kind.INVOICE or not refund_id:
        return None
    existing = PlatformGstInvoice.objects.filter(
        company=invoice.company, provider=invoice.provider, capture_id=refund_id,
    ).first()
    if existing is not None:
        return existing
    already = sum((cn.total for cn in invoice.credit_notes.all()), Decimal("0.00"))
    if _money(Decimal(str(amount))) + already > invoice.total:
        from core.exceptions import BusinessRuleError

        raise BusinessRuleError("Credit notes cannot exceed the invoice total.")
    return _issue(
        invoice.company, kind=PlatformGstInvoice.Kind.CREDIT_NOTE, provider=invoice.provider,
        capture_id=refund_id, amount=amount, user=user, original=invoice,
    )
