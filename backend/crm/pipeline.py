"""Lead capture, exact-match dedupe, and 30-day round-robin assignment."""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import re
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core import signing
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

CSV_MAX_BYTES = 2 * 1024 * 1024
CSV_MAX_ROWS = 2000
CSV_ERROR_LIMIT = 100
# What a column may be called in an uploaded file (compared lower-case with spaces as underscores).
CSV_COLUMN_ALIASES = {
    "name": {"name", "full_name", "lead_name", "customer_name", "contact_name"},
    "phone": {"phone", "mobile", "mobile_number", "phone_number", "contact", "contact_number", "whatsapp"},
    "email": {"email", "email_id", "e_mail", "email_address"},
    "message": {"message", "notes", "note", "remarks", "comment", "comments"},
    "campaign": {"campaign", "campaign_id"},
    "referral_code": {"referral_code", "referral", "code"},
    "state": {"state"},
    "gstin": {"gstin", "gst_no", "gst_number"},
    "address": {"address"},
    "source": {"source"},
}


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


def describe_candidates(company, candidates: dict) -> dict:
    """What staff need to decide a duplicate: who each match is, not just its id."""
    candidates = candidates or {}
    customers = Customer.objects.filter(company=company, pk__in=candidates.get("customers") or []).order_by("id")
    leads = Lead.objects.filter(company=company, pk__in=candidates.get("leads") or []).order_by("id")
    return {
        "customers": [
            {"id": row.id, "name": row.name, "phone": row.phone or "", "email": row.email or "", "gstin": row.gstin or ""}
            for row in customers
        ],
        "leads": [
            {
                "id": row.id, "name": row.name, "phone": row.phone or "", "email": row.email or "",
                "status": row.status, "last_touched_at": row.last_touched_at,
            }
            for row in leads
        ],
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
        # D13: a company with no sales staff still has someone to work its leads, the owner.
        return (
            CompanyUser.objects.select_for_update()
            .filter(
                company=company, role=CompanyUser.Role.OWNER, is_active=True, user__is_active=True,
            )
            .order_by("id")
            .first()
        )
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
    state: str = "",
    gstin: str = "",
    address: str = "",
) -> Lead:
    """Create a lead. Manual matches wait for an explicit decision."""
    if source and source not in SOURCES:
        raise BusinessRuleError("Unknown lead source.")
    gstin = (gstin or "").strip().upper()
    if gstin:
        from core.validators import GSTIN_RE

        if not GSTIN_RE.match(gstin):
            raise BusinessRuleError("Enter a valid 15-character GSTIN.")
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
        state=(state or "").strip(),
        gstin=gstin,
        address=(address or "").strip(),
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


def parse_lead_csv(raw: bytes) -> list[dict]:
    """Rows from an uploaded file, or a BusinessRuleError that says what is wrong with it."""
    if len(raw) > CSV_MAX_BYTES:
        raise BusinessRuleError(f"The file is larger than {CSV_MAX_BYTES // (1024 * 1024)} MB. Split it and upload again.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Excel on Windows saves "CSV" as cp1252, not UTF-8.
        text = raw.decode("cp1252", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise BusinessRuleError("The file is empty.")
    column_for = {}
    for header in reader.fieldnames:
        key = re.sub(r"[\s\-]+", "_", (header or "").strip().lower())
        for target, names in CSV_COLUMN_ALIASES.items():
            if key in names and target not in column_for.values():
                column_for[header] = target
                break
    if "name" not in column_for.values():
        raise BusinessRuleError("The file needs a Name column.")
    rows = []
    for raw_row in reader:
        if len(rows) >= CSV_MAX_ROWS:
            raise BusinessRuleError(f"The file has more than {CSV_MAX_ROWS:,} rows. Split it and upload again.")
        row = {target: (raw_row.get(header) or "").strip() for header, target in column_for.items()}
        if any(row.values()):
            rows.append(row)
    if not rows:
        raise BusinessRuleError("The file has no rows to import.")
    return rows


def import_lead_rows(company, user, rows: list[dict]) -> dict:
    created = 0
    review = 0
    errors = []
    error_count = 0
    for index, row in enumerate(rows, start=1):
        source = (row.get("source") or "").strip().lower().replace(" ", "_") or "import"
        try:
            lead = capture_lead(
                company,
                user,
                name=row.get("name") or "",
                phone=row.get("phone") or "",
                email=row.get("email") or "",
                message=row.get("message") or "",
                source=source if source in SOURCES else "import",
                manual=False,
                campaign=row.get("campaign") or None,
                referral_code=row.get("referral_code") or "",
                attribution_quiet=True,
                state=row.get("state") or "",
                gstin=row.get("gstin") or "",
                address=row.get("address") or "",
            )
        except (BusinessRuleError, ValidationError) as exc:
            error_count += 1
            if len(errors) < CSV_ERROR_LIMIT:
                detail = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
                errors.append({
                    "row": index, "detail": detail, "name": row.get("name") or "",
                    "phone": row.get("phone") or "", "email": row.get("email") or "",
                })
            continue
        created += 1
        if lead.dedupe_review == PENDING_REVIEW:
            review += 1
    return {
        "total": len(rows), "created": created, "pending_review": review,
        "error_count": error_count, "errors": errors,
    }


def verify_whatsapp_signature(body: bytes, header: str, secret: str) -> bool:
    if not secret or not header:
        return False
    prefix = "sha256="
    presented = header.strip()
    if presented.startswith(prefix):
        presented = presented[len(prefix):]
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, presented)


def company_whatsapp_secret(company) -> str:
    """This company's Meta app secret, else the server-wide one."""
    from django.conf import settings

    sealed = (getattr(company, "whatsapp_app_secret", "") or "").strip()
    if sealed:
        from planwave.crypto import open_secret

        try:
            return open_secret(sealed)
        except Exception:  # noqa: BLE001 — an unreadable secret must fail closed, not fall back
            return ""
    return getattr(settings, "WHATSAPP_APP_SECRET", "") or ""


def set_company_whatsapp_secret(company, secret: str) -> None:
    from accounts.models import Company
    from planwave.crypto import seal

    secret = (secret or "").strip()
    if len(secret) < 8:
        raise BusinessRuleError("Paste the app secret from your Meta app settings.")
    Company.objects.filter(pk=company.pk).update(whatsapp_app_secret=seal(secret))
    company.whatsapp_app_secret = seal(secret)


def parse_whatsapp_payload(payload) -> list[dict]:
    """Messages in a webhook body. Meta's nested format first, then the simple flat one.

    Delivery receipts and other events carry no ``messages`` and give an empty list.
    """
    if not isinstance(payload, dict):
        return []
    found = []
    for entry in payload.get("entry") or []:
        for change in (entry or {}).get("changes") or []:
            value = (change or {}).get("value") or {}
            names = {
                str(contact.get("wa_id") or ""): str((contact.get("profile") or {}).get("name") or "")
                for contact in value.get("contacts") or []
            }
            for message in value.get("messages") or []:
                sender = str(message.get("from") or "").strip()
                kind = str(message.get("type") or "text")
                if kind == "text":
                    text = str((message.get("text") or {}).get("body") or "")
                else:
                    text = f"[{kind} message]"
                digits = re.sub(r"\D", "", sender)
                found.append({
                    "message_id": str(message.get("id") or ""),
                    "sender": f"+{digits}" if digits and len(digits) > 10 else sender,
                    "name": names.get(sender, ""),
                    "text": text,
                    "sent_at": str(message.get("timestamp") or ""),
                })
    if found or "entry" in payload:
        return found
    message_id = str(payload.get("message_id") or payload.get("id") or "")
    sender = str(payload.get("from") or payload.get("sender") or "")
    if not message_id and not sender:
        return []
    return [{
        "message_id": message_id, "sender": sender, "name": "",
        "text": str(payload.get("text") or ""), "sent_at": str(payload.get("timestamp") or ""),
    }]


def ingest_whatsapp_message(
    company, *, message_id: str, sender: str, text: str, sent_at: str, name: str = "",
) -> Lead | None:
    """Idempotent inbound message. A retried id returns the existing lead."""
    key = (message_id or "").strip()
    if not key:
        raise BusinessRuleError("message id is required.")
    with transaction.atomic():
        existing = IdempotencyRecord.objects.filter(
            company=company, scope="whatsapp_inbound", key=key[:128]
        ).first()
        if existing and existing.resource_id:
            return Lead.objects.filter(company=company, pk=existing.resource_id).first()
        lead = capture_lead(
            company,
            None,
            name=(name or "").strip() or sender or "WhatsApp lead",
            phone=sender,
            message=text,
            source="whatsapp",
            manual=False,
        )
        try:
            # Own savepoint: a lost race on the unique key must not poison the outer transaction
            # (Postgres refuses every later statement once one fails).
            with transaction.atomic():
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


_CAMPAIGN_SALT = "crm.leadform.campaign"
_CAMPAIGN_MAX_AGE = 366 * 24 * 3600


def sign_campaign(campaign_id: int) -> str:
    """Campaign reference for a public link. It cannot be guessed or changed by the visitor."""
    return signing.dumps({"c": int(campaign_id)}, salt=_CAMPAIGN_SALT)


def unsign_campaign(value) -> int | None:
    if not value or not isinstance(value, str):
        return None
    try:
        data = signing.loads(value, salt=_CAMPAIGN_SALT, max_age=_CAMPAIGN_MAX_AGE)
    except signing.BadSignature:
        return None
    return int(data.get("c")) if isinstance(data, dict) and data.get("c") else None


def ensure_lead_form_token(company) -> str:
    """Mint the public form token once, under a row lock so two callers share it."""
    return _ensure_company_token(company, "lead_form_token", rotate=False)


def ensure_lead_form_token_rotated(company) -> str:
    """Replace the public form token; the old link stops working at once."""
    return _ensure_company_token(company, "lead_form_token", rotate=True)


def ensure_whatsapp_webhook_token(company, *, rotate: bool = False) -> str:
    """Mint the webhook token once. rotate replaces a token that already exists."""
    return _ensure_company_token(company, "whatsapp_webhook_token", rotate=rotate)


def ensure_whatsapp_verify_token(company, *, rotate: bool = False) -> str:
    """The token Meta echoes back during the handshake; separate from the URL token."""
    return _ensure_company_token(company, "whatsapp_verify_token", rotate=rotate)


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
