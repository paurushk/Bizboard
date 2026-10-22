"""WP-BL1: customers that deduct TDS on Bizboard's fees claim it back.

Card and UPI charges can't have TDS withheld, so the customer pays each invoice in full. After the
quarter they upload Form 16A for those invoices; staff check it against TRACES in Django admin and
verify. Settlement (Q5, founder 2026-10-22): by default the verified amount is a credit that comes
off the next renewal — when the renewal is charged, that much of it is refunded straight away, so
the customer's net payment drops. The owner can ask for a refund instead at any time while credit
is left; the rest is then refunded against the claimed invoices' own Razorpay payments. A TDS
refund isn't a price reduction, so neither path issues a GST credit note; Bizboard claims the TDS
against its own tax (the verified claims list in admin is that record, X-01).

Sections and rates are a CA-maintained setting (``SAAS_TDS_SECTIONS``); the owner picks one and the
amount is computed from the invoices' taxable value (TDS applies before GST).

``send_form16a_reminders`` (daily beat, acts on the 16th of Aug/Nov/Feb/Jun, the day after Form 16A
is due) reminds owners who paid Bizboard invoices with a GSTIN in the quarter and have not claimed.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessRuleError

from .models import PlatformGstInvoice, SaasTdsClaim

logger = logging.getLogger(__name__)

DEFAULT_SECTIONS = (
    ("194J-2", "194J technical services, 2%", "2"),
    ("194J-10", "194J professional services, 10%", "10"),
    ("194C-1", "194C contract, individual/HUF, 1%", "1"),
    ("194C-2", "194C contract, others, 2%", "2"),
)


def sections() -> list[dict]:
    rows = getattr(settings, "SAAS_TDS_SECTIONS", None) or DEFAULT_SECTIONS
    return [{"code": c, "label": label, "rate": Decimal(str(r))} for c, label, r in rows]


def _money(v) -> Decimal:
    return Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def fy_quarter(day) -> str:
    """``2026-27 Q2`` for a date in July–September 2026."""
    from .platform_gst import financial_year

    q = {4: 1, 5: 1, 6: 1, 7: 2, 8: 2, 9: 2, 10: 3, 11: 3, 12: 3, 1: 4, 2: 4, 3: 4}[day.month]
    return f"{financial_year(day)} Q{q}"


def submit_claim(
    *, company, user, invoice_ids, section_code: str, certificate_id: int, settle_by: str = "",
) -> SaasTdsClaim:
    from core.models import FileAsset

    section = next((s for s in sections() if s["code"] == section_code), None)
    if section is None:
        raise BusinessRuleError("Pick a TDS section from the list.", code="TDS_SECTION_UNKNOWN")
    settle_by = (settle_by or SaasTdsClaim.SettleBy.CREDIT).upper()
    if settle_by not in SaasTdsClaim.SettleBy.values:
        raise BusinessRuleError("Choose credit or refund.", code="TDS_SETTLE_UNKNOWN")
    ids = sorted({int(i) for i in invoice_ids or []})
    if not ids:
        raise BusinessRuleError("Pick at least one Bizboard invoice.", code="TDS_NO_INVOICES")
    certificate = FileAsset.objects.filter(company=company, pk=certificate_id).first()
    if certificate is None:
        raise BusinessRuleError("Upload the Form 16A certificate first.", code="TDS_NO_CERTIFICATE")
    with transaction.atomic():
        invoices = list(
            PlatformGstInvoice.objects.select_for_update()
            .filter(company=company, pk__in=ids, kind=PlatformGstInvoice.Kind.INVOICE)
            .order_by("pk")
        )
        if len(invoices) != len(ids):
            raise BusinessRuleError("Some of those invoices are not yours.", code="TDS_INVOICE_NOT_FOUND")
        taken = (
            SaasTdsClaim.objects.filter(company=company, invoices__in=invoices)
            .exclude(status=SaasTdsClaim.Status.REJECTED)
            .exists()
        )
        if taken:
            raise BusinessRuleError(
                "TDS for one of these invoices is already claimed.", code="TDS_ALREADY_CLAIMED",
            )
        taxable = sum((inv.taxable_amount for inv in invoices), Decimal("0.00"))
        claim = SaasTdsClaim.objects.create(
            company=company,
            section=section["code"],
            rate=section["rate"],
            taxable_total=_money(taxable),
            amount=_money(taxable * section["rate"] / 100),
            quarter=fy_quarter(timezone.localtime(max(inv.created_at for inv in invoices)).date()),
            certificate=certificate,
            settle_by=settle_by,
            created_by=user,
            updated_by=user,
        )
        claim.invoices.set(invoices)
    return claim


def _refund_amounts(claim: SaasTdsClaim) -> list[tuple[PlatformGstInvoice, Decimal]]:
    """Split the claim across its invoices; rounding goes on the last one so the parts add up."""
    invoices = list(claim.invoices.order_by("pk"))
    parts, running = [], Decimal("0.00")
    for i, inv in enumerate(invoices):
        part = claim.amount - running if i == len(invoices) - 1 else _money(inv.taxable_amount * claim.rate / 100)
        running += part
        parts.append((inv, part))
    return parts


def _refund_to_claimed_invoices(claim: SaasTdsClaim, budget: Decimal) -> None:
    """Refund up to ``budget`` against the claimed invoices' own payments (retry-safe)."""
    from .services import razorpay_refund

    done = {r.get("invoice") for r in claim.refund_ids}
    for inv, part in _refund_amounts(claim):
        part = min(part, budget)
        if inv.pk in done or part <= 0:
            continue
        if inv.provider != "razorpay":
            raise BusinessRuleError(f"Invoice {inv.number} was not paid through Razorpay; refund it by hand.")
        refund_id = razorpay_refund(inv.capture_id, int(part * 100), notes={"tds_claim": claim.pk})
        budget -= part
        claim.refund_ids = [*claim.refund_ids, {"invoice": inv.pk, "refund": refund_id, "amount": str(part)}]
        claim.save(update_fields=["refund_ids", "updated_at"])


def _refunded(claim: SaasTdsClaim) -> Decimal:
    return sum((Decimal(r["amount"]) for r in claim.refund_ids), Decimal("0.00"))


def _credited(claim: SaasTdsClaim) -> Decimal:
    return sum((Decimal(r["amount"]) for r in claim.credit_applied), Decimal("0.00"))


def verify_claim(claim: SaasTdsClaim, *, staff_user, note: str = "") -> SaasTdsClaim:
    """Staff checked the certificate in TRACES. Credit claims wait for the next renewal; refund
    claims are refunded now against each claimed invoice's Razorpay payment."""
    if claim.status not in (SaasTdsClaim.Status.SUBMITTED, SaasTdsClaim.Status.VERIFIED):
        raise BusinessRuleError(f"Claim is {claim.get_status_display().lower()}.")
    first_check = claim.status == SaasTdsClaim.Status.SUBMITTED
    claim.status = SaasTdsClaim.Status.VERIFIED
    claim.reviewed_by = staff_user
    claim.reviewed_at = claim.reviewed_at or timezone.now()
    claim.review_note = (note or claim.review_note or "")[:500]
    if first_check:
        claim.credit_remaining = claim.amount
    claim.save(update_fields=[
        "status", "reviewed_by", "reviewed_at", "review_note", "credit_remaining", "updated_at",
    ])
    if claim.settle_by == SaasTdsClaim.SettleBy.REFUND:
        return _settle_by_refund(claim)
    if first_check:
        _notify(claim, f"Your TDS claim of {claim.amount} for {claim.quarter} is accepted. "
                       "It will come off your next renewal.")
    return claim


# Kept for callers and tests written before Q5 (refund-only settlement).
verify_and_refund = verify_claim


def _settle_by_refund(claim: SaasTdsClaim) -> SaasTdsClaim:
    budget = claim.amount - _credited(claim) - _refunded(claim)
    _refund_to_claimed_invoices(claim, budget)
    claim.credit_remaining = Decimal("0.00")
    claim.status = SaasTdsClaim.Status.SETTLED
    claim.save(update_fields=["credit_remaining", "status", "updated_at"])
    _notify(claim, f"Your TDS claim for {claim.quarter} is settled: {_refunded(claim)} refunded"
                   + (f", {_credited(claim)} taken off renewals." if _credited(claim) else "."))
    return claim


def request_refund(claim: SaasTdsClaim, *, user) -> SaasTdsClaim:
    """The owner asks for the credit still left on a claim to be refunded instead."""
    with transaction.atomic():
        claim = SaasTdsClaim.objects.select_for_update().get(pk=claim.pk)
        if claim.status == SaasTdsClaim.Status.SETTLED or claim.status == SaasTdsClaim.Status.REJECTED:
            raise BusinessRuleError("This claim is already closed.", code="TDS_CLAIM_CLOSED")
        claim.settle_by = SaasTdsClaim.SettleBy.REFUND
        claim.updated_by = user
        claim.save(update_fields=["settle_by", "updated_by", "updated_at"])
    if claim.status == SaasTdsClaim.Status.SUBMITTED:
        return claim  # refunded when staff verify it
    return _settle_by_refund(claim)


def apply_renewal_credit(company, invoice: PlatformGstInvoice) -> Decimal:
    """Take verified TDS credit off a renewal: refund up to the renewal's total against its own
    payment. Called after a Razorpay renewal invoice is issued, and by the daily recon for any
    renewal the webhook path missed. Returns the amount applied (0 when nothing to do)."""
    from .services import razorpay_refund

    if invoice.kind != PlatformGstInvoice.Kind.INVOICE or invoice.provider != "razorpay":
        return Decimal("0.00")
    applied_total = Decimal("0.00")
    with transaction.atomic():
        claims = list(
            SaasTdsClaim.objects.select_for_update()
            .filter(
                company=company, status=SaasTdsClaim.Status.VERIFIED,
                settle_by=SaasTdsClaim.SettleBy.CREDIT, credit_remaining__gt=0,
            )
            .order_by("reviewed_at", "pk")
        )
        used_on_invoice = sum(
            (Decimal(r["amount"]) for c in SaasTdsClaim.objects.filter(company=company)
             for r in c.credit_applied if r.get("invoice") == invoice.pk),
            Decimal("0.00"),
        )
        room = invoice.total - used_on_invoice
        for claim in claims:
            if room <= 0:
                break
            if claim.reviewed_at and invoice.created_at < claim.reviewed_at:
                continue  # only renewals after the claim was accepted
            if claim in invoice.tds_claims.all():
                continue  # never credit a claim against an invoice it claims TDS on
            part = min(claim.credit_remaining, room)
            refund_id = razorpay_refund(invoice.capture_id, int(part * 100), notes={"tds_credit": claim.pk})
            claim.credit_applied = [
                *claim.credit_applied, {"invoice": invoice.pk, "refund": refund_id, "amount": str(part)},
            ]
            claim.credit_remaining -= part
            if claim.credit_remaining <= 0:
                claim.credit_remaining = Decimal("0.00")
                claim.status = SaasTdsClaim.Status.SETTLED
            claim.save(update_fields=["credit_applied", "credit_remaining", "status", "updated_at"])
            room -= part
            applied_total += part
            if claim.status == SaasTdsClaim.Status.SETTLED:
                _notify(claim, f"Your TDS claim for {claim.quarter} is settled: {_credited(claim)} "
                               f"taken off your renewal {invoice.number}.")
    return applied_total


def apply_pending_credits() -> int:
    """Daily recon: apply credit to Razorpay renewals issued since a claim was verified."""
    from core.rls import rls_bypass

    applied = 0
    with rls_bypass():
        company_ids = set(
            SaasTdsClaim.objects.filter(
                status=SaasTdsClaim.Status.VERIFIED, settle_by=SaasTdsClaim.SettleBy.CREDIT,
                credit_remaining__gt=0,
            ).values_list("company_id", flat=True)
        )
        for cid in company_ids:
            first = (
                SaasTdsClaim.objects.filter(company_id=cid, status=SaasTdsClaim.Status.VERIFIED)
                .order_by("reviewed_at").first()
            )
            renewals = PlatformGstInvoice.objects.filter(
                company_id=cid, kind=PlatformGstInvoice.Kind.INVOICE, provider="razorpay",
                created_at__gte=first.reviewed_at,
            ).order_by("created_at")
            for inv in renewals:
                try:
                    if apply_renewal_credit(inv.company, inv) > 0:
                        applied += 1
                except Exception:  # noqa: BLE001 - one company's gateway error must not stop the rest
                    logger.exception("TDS credit on renewal %s failed; retried tomorrow", inv.pk)
    return applied


def reject(claim: SaasTdsClaim, *, staff_user, reason: str) -> SaasTdsClaim:
    if claim.status in (SaasTdsClaim.Status.SETTLED, SaasTdsClaim.Status.VERIFIED):
        raise BusinessRuleError("An accepted claim can't be rejected.")
    if not (reason or "").strip():
        raise BusinessRuleError("Say why the claim is rejected.")
    claim.status = SaasTdsClaim.Status.REJECTED
    claim.reviewed_by = staff_user
    claim.reviewed_at = timezone.now()
    claim.review_note = reason.strip()[:500]
    claim.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"])
    _notify(claim, f"Your TDS claim for {claim.quarter} was not accepted: {claim.review_note}")
    return claim


# Form 16A for a quarter is due on the 15th of the month after the TDS return (Q1 Aug, Q2 Nov,
# Q3 Feb, Q4 Jun). Remind the day after.
_REMINDER_MONTHS = {8: (4, 6, 0), 11: (7, 9, 0), 2: (10, 12, -1), 6: (1, 3, 0)}


def _quarter_window(today: date) -> tuple[date, date] | None:
    spec = _REMINDER_MONTHS.get(today.month)
    if spec is None or today.day != 16:
        return None
    first_month, last_month, year_shift = spec
    year = today.year + year_shift
    start = date(year, first_month, 1)
    end = date(year + (1 if last_month == 12 else 0), 1 if last_month == 12 else last_month + 1, 1)
    return start, end


def send_form16a_reminders(today: date | None = None) -> int:
    """Remind owners to claim TDS for last quarter's Bizboard invoices. Once per company and quarter."""
    from core.models import Notification
    from core.rls import rls_bypass
    from core.services.notifications import NotificationService

    today = today or timezone.localdate()
    window = _quarter_window(today)
    if window is None:
        return 0
    start, end = window
    quarter = fy_quarter(start)
    subject = f"Claim back TDS for {quarter}"
    sent = 0
    with rls_bypass():
        invoices = PlatformGstInvoice.objects.filter(
            kind=PlatformGstInvoice.Kind.INVOICE, created_at__date__gte=start, created_at__date__lt=end,
        ).exclude(buyer_gstin="").select_related("company")
        by_company: dict[int, list[PlatformGstInvoice]] = {}
        for inv in invoices:
            by_company.setdefault(inv.company_id, []).append(inv)
        for cid, rows in by_company.items():
            company = rows[0].company
            unclaimed = [
                inv for inv in rows
                if not inv.tds_claims.exclude(status=SaasTdsClaim.Status.REJECTED).exists()
            ]
            if not unclaimed or not getattr(company, "email", ""):
                continue
            if Notification.objects.filter(company_id=cid, subject=subject).exists():
                continue
            numbers = ", ".join(inv.number for inv in unclaimed[:10])
            NotificationService.send(
                company=company, channel=Notification.Channel.EMAIL, recipient=company.email,
                subject=subject,
                body=(f"If you deducted TDS on Bizboard invoices {numbers}, attach Form 16A under "
                      "Billing → Bizboard invoices. The amount comes off your next renewal, or we "
                      "refund it if you ask."),
            )
            sent += 1
    return sent


def _notify(claim: SaasTdsClaim, body: str) -> None:
    from core.models import Notification
    from core.services.notifications import NotificationService

    company = claim.company
    if getattr(company, "email", ""):
        NotificationService.send(
            company=company, channel=Notification.Channel.EMAIL, recipient=company.email,
            subject="TDS claim update", body=body,
        )
    NotificationService.send(
        company=company, channel=Notification.Channel.IN_APP, recipient=company.email or str(company.pk),
        subject="TDS claim update", body=body,
    )
