"""Lead capture, exact-match dedupe, and 30-day round-robin assignment."""

from __future__ import annotations

import hashlib
import hmac
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.utils import timezone

from accounts.models import CompanyUser
from accounts.otp_utils import canonicalize_user_phone, phone_lookup_values
from core.exceptions import BusinessRuleError
from core.services.round_robin import pick_least_loaded
from core.models import IdempotencyRecord
from masters.models import Customer

from .models import Lead

SOURCES = {"referral", "website", "whatsapp", "walk_in", "import", "phone"}
PENDING_REVIEW = "PENDING_REVIEW"


class DedupePrompt(BusinessRuleError):
    """Manual capture found a match. The client shows a merge prompt."""

    def __init__(self, candidates: dict):
        super().__init__("This phone or email already exists.", code="dedupe_match")
        self.candidates = candidates


def _canon_phone(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    try:
        return canonicalize_user_phone(raw)
    except ValueError:
        return raw


def find_candidates(company, phone: str, email: str, *, exclude_lead_id=None) -> dict:
    phones = phone_lookup_values(phone) if phone else []
    email = (email or "").strip()
    customers = []
    leads = []
    # A converted lead's own customer record already appears in `customers`;
    # counting the source lead too would make every repeat contact from a
    # converted customer look like a 2-party ambiguous match forever.
    if phones:
        customers.extend(
            Customer.objects.filter(company=company, phone__in=phones).values_list("id", flat=True)
        )
        lead_qs = Lead.objects.filter(company=company, phone__in=phones, customer__isnull=True)
        if exclude_lead_id:
            lead_qs = lead_qs.exclude(pk=exclude_lead_id)
        leads.extend(lead_qs.values_list("id", flat=True))
    if email:
        customers.extend(
            Customer.objects.filter(company=company, email__iexact=email).values_list("id", flat=True)
        )
        lead_qs = Lead.objects.filter(company=company, email__iexact=email, customer__isnull=True)
        if exclude_lead_id:
            lead_qs = lead_qs.exclude(pk=exclude_lead_id)
        leads.extend(lead_qs.values_list("id", flat=True))
    return {
        "customers": sorted(set(customers)),
        "leads": sorted(set(leads)),
    }


def _ambiguous(candidates: dict) -> bool:
    parties = len(candidates["customers"]) + len(candidates["leads"])
    return parties > 1


def _single(candidates: dict):
    if _ambiguous(candidates) or not (candidates["customers"] or candidates["leads"]):
        return None, None
    customer_id = candidates["customers"][0] if candidates["customers"] else None
    lead_id = candidates["leads"][0] if candidates["leads"] else None
    return customer_id, lead_id


def next_assignee(company):
    from django.db import transaction

    with transaction.atomic():
        return _next_assignee_locked(company)


def _next_assignee_locked(company):
    members = list(
        CompanyUser.objects.select_for_update()
        .filter(
            company=company,
            role=CompanyUser.Role.SALES_STAFF,
            is_active=True,
            user__is_active=True,
        )
        .order_by("id")
    )
    if not members:
        return None
    since = timezone.now() - timedelta(days=30)
    counts = {
        row["assigned_to"]: row["c"]
        for row in (
            Lead.objects.filter(
                company=company,
                assigned_to__in=members,
                created_at__gte=since,
            )
            .values("assigned_to")
            .annotate(c=Count("id"))
        )
    }
    return pick_least_loaded(members, counts)


def _apply_match(lead: Lead, candidates: dict, *, review: bool) -> Lead:
    lead.dedupe_candidates = candidates
    customer_id, lead_id = _single(candidates)
    if review or _ambiguous(candidates):
        lead.dedupe_review = PENDING_REVIEW
        lead.dedupe_matched_customer_id = customer_id
        lead.dedupe_matched_lead_id = lead_id
    elif customer_id or lead_id:
        lead.dedupe_matched_customer_id = customer_id
        lead.dedupe_matched_lead_id = lead_id
        lead.dedupe_review = ""
    return lead


@transaction.atomic
def capture_lead(
    company,
    user,
    *,
    name: str,
    phone: str = "",
    email: str = "",
    message: str = "",
    source: str | None = None,
    manual: bool = False,
    dedupe_decision: str = "",
    campaign=None,
    referral_code: str = "",
    attribution_quiet: bool = False,
) -> Lead:
    """Create a lead. Manual matches wait for an explicit decision."""
    if source and source not in SOURCES:
        raise BusinessRuleError("Unknown lead source.")
    phone = _canon_phone(phone)
    email = (email or "").strip()
    if not (name or "").strip():
        raise BusinessRuleError("Name is required.")
    # A lead with neither contact field has nothing to dedupe against — it's
    # still a valid manual capture (e.g. jotting a name down during a call
    # before getting the rest), it just never matches an existing party. But
    # an automated source (CSV import, webhook, public web form) with neither
    # field is almost always a malformed/misaligned row, not a deliberate
    # contactless lead, so it must still fail loudly per-row.
    if not manual and not phone and not email:
        raise BusinessRuleError("Enter a phone number or an email.")
    candidates = find_candidates(company, phone, email)
    has_match = bool(candidates["customers"] or candidates["leads"])
    if manual and has_match and dedupe_decision not in {"create", "review"}:
        raise DedupePrompt(candidates)
    # Only an explicit review decision (or genuine ambiguity, applied below
    # by _apply_match) sends a lead to PENDING_REVIEW. A single clean match
    # on an async channel (webhook/CSV/web-form) auto-routes normally, with
    # the match recorded for reference — it must not be indistinguishable
    # from a real multi-party ambiguity.
    review = dedupe_decision == "review"
    assignee = None if review else next_assignee(company)
    from .referrals import resolve_campaign, resolve_referral_code

    campaign_row = resolve_campaign(company, campaign, quiet=attribution_quiet or not manual)
    referral_row = resolve_referral_code(company, referral_code)
    lead = Lead(
        company=company,
        name=name.strip(),
        phone=phone,
        email=email,
        message=(message or "").strip(),
        source=source,
        campaign=campaign_row,
        referral_code=referral_row,
        assigned_to=assignee,
        created_by=user,
        updated_by=user,
    )
    _apply_match(lead, candidates, review=review)
    lead.save()
    from insights.telemetry import note_once

    note_once(company, "first_lead", user=user, journey="growth")
    return lead


def import_lead_rows(company, user, rows: list[dict]) -> dict:
    created = 0
    review = 0
    errors = []
    for index, row in enumerate(rows, start=1):
        try:
            lead = capture_lead(
                company,
                user,
                name=row.get("name") or "",
                phone=row.get("phone") or "",
                email=row.get("email") or "",
                message=row.get("message") or "",
                source="import",
                manual=False,
                campaign=row.get("campaign") or None,
                referral_code=row.get("referral_code") or "",
                attribution_quiet=True,
            )
        except (BusinessRuleError, ValidationError) as exc:
            errors.append({"row": index, "detail": str(exc)})
            continue
        created += 1
        if lead.dedupe_review == PENDING_REVIEW:
            review += 1
    return {"created": created, "pending_review": review, "errors": errors}


def verify_whatsapp_signature(body: bytes, header: str, secret: str) -> bool:
    if not secret or not header:
        return False
    prefix = "sha256="
    presented = header.strip()
    if presented.startswith(prefix):
        presented = presented[len(prefix):]
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, presented)


@transaction.atomic
def ingest_whatsapp_message(company, *, message_id: str, sender: str, text: str, sent_at: str) -> Lead | None:
    """Idempotent inbound message. A retried id returns the existing lead."""
    key = (message_id or "").strip()
    if not key:
        raise BusinessRuleError("message id is required.")
    existing = IdempotencyRecord.objects.filter(
        company=company, scope="whatsapp_inbound", key=key[:128]
    ).first()
    if existing and existing.resource_id:
        return Lead.objects.filter(company=company, pk=existing.resource_id).first()
    lead = capture_lead(
        company,
        None,
        name=sender or "WhatsApp lead",
        phone=sender,
        message=text,
        source="whatsapp",
        manual=False,
    )
    try:
        IdempotencyRecord.objects.create(
            company=company,
            scope="whatsapp_inbound",
            key=key[:128],
            status_code=200,
            body={"sent_at": sent_at, "text": text[:2000]},
            resource_id=str(lead.id),
        )
    except IntegrityError:
        lead.delete()
        winner = IdempotencyRecord.objects.get(
            company=company, scope="whatsapp_inbound", key=key[:128]
        )
        return Lead.objects.filter(company=company, pk=winner.resource_id).first()
    return lead


def ensure_lead_form_token(company) -> str:
    """Mint the public form token once, under a row lock so two callers share it."""
    return _ensure_company_token(company, "lead_form_token", rotate=False)


def ensure_whatsapp_webhook_token(company, *, rotate: bool = False) -> str:
    """Mint the webhook token once. rotate replaces a token that already exists."""
    return _ensure_company_token(company, "whatsapp_webhook_token", rotate=rotate)


def _ensure_company_token(company, field: str, *, rotate: bool) -> str:
    import secrets

    from accounts.models import Company

    with transaction.atomic():
        locked = Company.objects.select_for_update().get(pk=company.pk)
        current = getattr(locked, field) or ""
        if current and not rotate:
            setattr(company, field, current)
            return current
        minted = secrets.token_urlsafe(24)
        setattr(locked, field, minted)
        locked.save(update_fields=[field, "updated_at"])
        setattr(company, field, minted)
        return minted
