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


def _int_ids(values) -> list[int]:
    """A JSON list of invoice ids; anything else (a bare number, a string) is refused, not guessed."""
    if values in (None, ""):
        return []
    if not isinstance(values, (list, tuple, set)):
        raise BusinessRuleError("Send the invoice ids as a list.", code="TDS_NO_INVOICES")
    try:
        return sorted({int(i) for i in values})
    except (TypeError, ValueError):
        raise BusinessRuleError("Some of those invoices are not yours.", code="TDS_INVOICE_NOT_FOUND") from None


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
    ids = _int_ids(invoice_ids)
    if not ids:
        raise BusinessRuleError("Pick at least one Bizboard invoice.", code="TDS_NO_INVOICES")
    try:
        certificate_id = int(certificate_id or 0)
    except (TypeError, ValueError):
        certificate_id = 0
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


def _refundable_or_raise(claim: SaasTdsClaim) -> None:
    """A refund goes back on each claimed invoice's own Razorpay payment; refuse before changing
    anything when that is impossible, so the claim is never left half-switched."""
    key = (getattr(settings, "RAZORPAY_KEY_ID", "") or "").strip()
    secret = (getattr(settings, "RAZORPAY_KEY_SECRET", "") or "").strip()
    if not key or not secret:
        raise BusinessRuleError("Refunds are not available right now; the credit stays on your next renewal.",
                                code="TDS_REFUND_UNAVAILABLE")
    for inv in claim.invoices.all():
        if inv.provider != "razorpay" or not inv.capture_id:
            raise BusinessRuleError(
                f"Invoice {inv.number} was not paid through Razorpay; ask support to refund it by hand.",
                code="TDS_REFUND_UNAVAILABLE",
            )


def _refund_to_claimed_invoices(claim_pk: int) -> SaasTdsClaim:
    """Refund what is left of a claim against the claimed invoices' own payments.

    Each invoice is its own transaction: the claim row is locked and re-read, the refund is sent
    with an idempotency key for that (claim, invoice), and the refund id is committed before the
    next one. A second caller waits on the lock and then sees the invoice done, and a failure on a
    later invoice never rolls back the record of a refund already made.
    """
    from .services import razorpay_refund

    claim = SaasTdsClaim.objects.get(pk=claim_pk)
    for inv, part in _refund_amounts(claim):
        with transaction.atomic():
            claim = SaasTdsClaim.objects.select_for_update().get(pk=claim_pk)
            done = {r.get("invoice") for r in claim.refund_ids}
            budget = claim.amount - _credited(claim) - _refunded(claim)
            part = min(part, budget)
            if inv.pk in done or part <= 0:
                continue
            if inv.provider != "razorpay":
                raise BusinessRuleError(f"Invoice {inv.number} was not paid through Razorpay; refund it by hand.")
            refund_id = razorpay_refund(
                inv.capture_id, int(part * 100), notes={"tds_claim": claim.pk},
                idempotency_key=f"tds-refund-{claim.pk}-{inv.pk}",
            )
            claim.refund_ids = [*claim.refund_ids, {"invoice": inv.pk, "refund": refund_id, "amount": str(part)}]
            claim.save(update_fields=["refund_ids", "updated_at"])
    return SaasTdsClaim.objects.get(pk=claim_pk)


def _refunded(claim: SaasTdsClaim) -> Decimal:
    return sum((Decimal(r["amount"]) for r in claim.refund_ids), Decimal("0.00"))


def _credited(claim: SaasTdsClaim) -> Decimal:
    return sum((Decimal(r["amount"]) for r in claim.credit_applied), Decimal("0.00"))


def verify_claim(claim: SaasTdsClaim, *, staff_user, note: str = "") -> SaasTdsClaim:
    """Staff checked the certificate in TRACES. Credit claims wait for the next renewal; refund
    claims are refunded now against each claimed invoice's Razorpay payment."""
    with transaction.atomic():
        claim = SaasTdsClaim.objects.select_for_update().get(pk=claim.pk)
        if claim.status not in (SaasTdsClaim.Status.SUBMITTED, SaasTdsClaim.Status.VERIFIED):
            raise BusinessRuleError(f"Claim is {claim.get_status_display().lower()}.")
        first_check = claim.status == SaasTdsClaim.Status.SUBMITTED
        claim.status = SaasTdsClaim.Status.VERIFIED
        claim.reviewed_by = staff_user
        claim.reviewed_at = claim.reviewed_at or timezone.now()
        claim.review_note = (note or claim.review_note or "")[:500]
        fields = ["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"]
        if first_check:
            claim.credit_remaining = claim.amount
            fields.append("credit_remaining")
        claim.save(update_fields=fields)
    if claim.settle_by == SaasTdsClaim.SettleBy.REFUND:
        return _settle_by_refund(claim)
    if first_check:
        _notify(claim, f"Your TDS claim of {claim.amount} for {claim.quarter} is accepted. "
                       "It will come off your next renewal.")
    return claim


def _settle_by_refund(claim: SaasTdsClaim) -> SaasTdsClaim:
    _refund_to_claimed_invoices(claim.pk)
    with transaction.atomic():
        claim = SaasTdsClaim.objects.select_for_update().get(pk=claim.pk)
        if claim.status == SaasTdsClaim.Status.SETTLED:
            return claim  # another caller finished it
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
        _refundable_or_raise(claim)
        previous = claim.settle_by
        claim.settle_by = SaasTdsClaim.SettleBy.REFUND
        claim.updated_by = user
        claim.save(update_fields=["settle_by", "updated_by", "updated_at"])
    if claim.status == SaasTdsClaim.Status.SUBMITTED:
        return claim  # refunded when staff verify it
    try:
        return _settle_by_refund(claim)
    except Exception:
        # Nothing went out: put the claim back on credit so it still comes off the next renewal.
        with transaction.atomic():
            fresh = SaasTdsClaim.objects.select_for_update().get(pk=claim.pk)
            if not fresh.refund_ids and fresh.status == SaasTdsClaim.Status.VERIFIED:
                fresh.settle_by = previous
                fresh.save(update_fields=["settle_by", "updated_at"])
        raise


def apply_renewal_credit(company, invoice: PlatformGstInvoice) -> Decimal:
    """Take verified TDS credit off a renewal: refund up to the renewal's total against its own
    payment. Called after a Razorpay renewal invoice is issued, and by the daily recon for any
    renewal the webhook path missed. Returns the amount applied (0 when nothing to do).

    One transaction per claim, with the renewal invoice row locked so the webhook and the daily
    task never both apply credit to it; each refund carries an idempotency key and is committed
    before the next, so a later failure can't erase the record of a refund already sent.
    """
    from .services import razorpay_refund

    if invoice.kind != PlatformGstInvoice.Kind.INVOICE or invoice.provider != "razorpay":
        return Decimal("0.00")
    claim_ids = list(
        SaasTdsClaim.objects.filter(
            company=company, status=SaasTdsClaim.Status.VERIFIED,
            settle_by=SaasTdsClaim.SettleBy.CREDIT, credit_remaining__gt=0,
        ).order_by("reviewed_at", "pk").values_list("pk", flat=True)
    )
    claimed_on_invoice = set(invoice.tds_claims.values_list("pk", flat=True))
    applied_total = Decimal("0.00")
    for claim_pk in claim_ids:
        if claim_pk in claimed_on_invoice:
            continue  # never credit a claim against an invoice it claims TDS on
        with transaction.atomic():
            PlatformGstInvoice.objects.select_for_update().filter(pk=invoice.pk).first()
            claim = SaasTdsClaim.objects.select_for_update().get(pk=claim_pk)
            if (claim.status != SaasTdsClaim.Status.VERIFIED or claim.settle_by != SaasTdsClaim.SettleBy.CREDIT
                    or claim.credit_remaining <= 0):
                continue
            if claim.reviewed_at and invoice.created_at < claim.reviewed_at:
                continue  # only renewals after the claim was accepted
            if any(r.get("invoice") == invoice.pk for r in claim.credit_applied):
                continue
            used_on_invoice = sum(
                (Decimal(r["amount"])
                 for applied in SaasTdsClaim.objects.filter(company=company)
                 .values_list("credit_applied", flat=True)
                 for r in applied if r.get("invoice") == invoice.pk),
                Decimal("0.00"),
            )
            room = invoice.total - used_on_invoice
            if room <= 0:
                break
            part = min(claim.credit_remaining, room)
            refund_id = razorpay_refund(
                invoice.capture_id, int(part * 100), notes={"tds_credit": claim.pk},
                idempotency_key=f"tds-credit-{claim.pk}-{invoice.pk}",
            )
            claim.credit_applied = [
                *claim.credit_applied, {"invoice": invoice.pk, "refund": refund_id, "amount": str(part)},
            ]
            claim.credit_remaining -= part
            if claim.credit_remaining <= 0:
                claim.credit_remaining = Decimal("0.00")
                claim.status = SaasTdsClaim.Status.SETTLED
            claim.save(update_fields=["credit_applied", "credit_remaining", "status", "updated_at"])
            applied_total += part
            if claim.status == SaasTdsClaim.Status.SETTLED:
                body = (f"Your TDS claim for {claim.quarter} is settled: {_credited(claim)} "
                        f"taken off your renewal {invoice.number}.")
                transaction.on_commit(lambda c=claim, b=body: _notify(c, b))
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
            if first is None or first.reviewed_at is None:
                continue  # settled meanwhile (e.g. by a renewal webhook)
            renewals = PlatformGstInvoice.objects.filter(
                company_id=cid, kind=PlatformGstInvoice.Kind.INVOICE, provider="razorpay",
                created_at__gte=first.reviewed_at,
            ).select_related("company").order_by("created_at")
            for inv in renewals:
                try:
                    if apply_renewal_credit(inv.company, inv) > 0:
                        applied += 1
                except Exception:  # noqa: BLE001 - one company's gateway error must not stop the rest
                    logger.exception("TDS credit on renewal %s failed; retried tomorrow", inv.pk)
    return applied


def reject(claim: SaasTdsClaim, *, staff_user, reason: str) -> SaasTdsClaim:
    if not (reason or "").strip():
        raise BusinessRuleError("Say why the claim is rejected.")
    with transaction.atomic():
        claim = SaasTdsClaim.objects.select_for_update().get(pk=claim.pk)
        if claim.status in (SaasTdsClaim.Status.SETTLED, SaasTdsClaim.Status.VERIFIED):
            raise BusinessRuleError("An accepted claim can't be rejected.")
        if claim.status != SaasTdsClaim.Status.SUBMITTED:
            raise BusinessRuleError("This claim was already rejected.")
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
