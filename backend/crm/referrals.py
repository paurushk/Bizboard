"""Referral codes and per-won-deal reward snapshots."""

from __future__ import annotations

import logging
import secrets
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.services.audit import AuditService
from core.services.feature_flags import flag_enabled
from core.services.flag_observability import log_flag_event

from .models import ReferralCode, ReferralReward
from .pipeline import _canon_phone

logger = logging.getLogger("bizboard.crm")

_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

# Security addendum (2026-09-25): a referrer could otherwise issue a code and
# have a "referred" lead resolve back to themselves, collecting a reward for
# referring themselves. Two independent guards below close that gap:
#   1. a daily cap on code *issuance* per referrer (this is a resource-abuse
#      control, not a fraud judgment — it just stops a scripted loop from
#      minting unlimited codes), and
#   2. an identity comparison at conversion time, before a reward row for a
#      won opportunity is created (the actual fraud check).

# Codes are reusable (one code serves many leads, per the locked G5 plan), so
# `ReferralCode.created_at` already tells us "how many times did this
# referrer ask for a brand-new code," without a second table. A dedicated
# `ReferralIssuanceLog` model was considered and dropped — it would only
# duplicate a column `ReferralCode` already has via `CompanyScopedModel`.
#
# 5/day is a deliberately loose default: legitimate re-issuance (a customer
# lost their code, support re-sends one) is rare but real, so this is sized
# to never bother an honest user while still bounding a scripted abuse loop
# to a handful of rows a day instead of thousands.
DAILY_ISSUANCE_LIMIT = 5


def _company_local_day_window(company):
    """Start/end of "today" in the company's locale, as aware datetimes.

    Duplicates the seam documented on `insights.alerts._company_localtime`
    (every current tenant lives in `settings.TIME_ZONE` — Asia/Kolkata — so
    this is server-local time today; a per-company timezone field would only
    need to change this one function) rather than importing it: `crm` does
    not depend on `insights`, and this app already keeps its own small
    time/phone helpers (see `crm.pipeline._canon_phone`) instead of reaching
    across bounded contexts.

    Boundaries are computed in Python and compared as timezone-aware
    datetimes (not a `created_at__date=` lookup) because dev/CI runs SQLite
    and prod runs Postgres, and the two backends do not extract a calendar
    date from a stored UTC timestamp the same way — the same reason
    `contracts/status.py` keeps its status date math in Python.
    """
    tzname = getattr(company, "timezone", None) or getattr(company, "time_zone", None)
    tz = None
    if tzname:
        try:
            from zoneinfo import ZoneInfo

            tz = ZoneInfo(str(tzname))
        except Exception:  # noqa: BLE001 — bad tz string falls back to server zone
            tz = None
    now_local = timezone.localtime(timezone=tz) if tz else timezone.localtime()
    start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _assert_issuance_rate_limit(company, *, referrer_customer, referrer_user):
    start, end = _company_local_day_window(company)
    qs = ReferralCode.objects.filter(company=company, created_at__gte=start, created_at__lt=end)
    qs = (
        qs.filter(referrer_customer=referrer_customer)
        if referrer_customer is not None
        else qs.filter(referrer_user=referrer_user)
    )
    issued_today = qs.count()
    if issued_today < DAILY_ISSUANCE_LIMIT:
        return
    log_flag_event(
        company,
        "ENABLE_REFERRALS",
        "referral_issuance_rate_limited",
        referrer_customer_id=getattr(referrer_customer, "id", None),
        referrer_user_id=getattr(referrer_user, "id", None),
        issued_today=issued_today,
    )
    raise BusinessRuleError(
        f"Daily referral code issuance limit ({DAILY_ISSUANCE_LIMIT} per referrer) reached. "
        "Try again tomorrow.",
        code="referral_issuance_rate_limited",
    )


def issue_referral_code(company, user, *, referrer_customer=None, referrer_user=None, reward_type="FLAT", reward_value=0):
    if (referrer_customer is None) == (referrer_user is None):
        raise BusinessRuleError("Set exactly one referrer.")
    # Defense in depth: `ReferralCodeViewSet.issue` already resolves
    # `referrer_customer`/`referrer_user` with a `company=` filter before
    # calling here, so a cross-tenant id 404s before this function ever runs.
    # This service function can be called from other paths in the future
    # (CSV import, admin tooling), so it re-asserts the same tenant boundary
    # itself rather than trusting every future caller to have done it.
    if referrer_customer is not None and referrer_customer.company_id != company.id:
        raise BusinessRuleError("Referrer customer must belong to this company.")
    if referrer_user is not None and referrer_user.company_id != company.id:
        raise BusinessRuleError("Referrer user must belong to this company.")
    _assert_issuance_rate_limit(company, referrer_customer=referrer_customer, referrer_user=referrer_user)
    from .models import ReferralCode

    reward_type = (reward_type or ReferralCode.RewardType.FLAT).strip().upper()
    if reward_type not in {ReferralCode.RewardType.FLAT, ReferralCode.RewardType.PERCENT}:
        raise BusinessRuleError("Reward type must be FLAT or PERCENT.")
    try:
        value = Decimal(str(reward_value if reward_value is not None else 0))
    except Exception as exc:
        raise BusinessRuleError("Reward value must be a number.") from exc
    if value < 0:
        raise BusinessRuleError("Reward value cannot be negative.")
    if reward_type == ReferralCode.RewardType.PERCENT and value > Decimal("100"):
        raise BusinessRuleError("A percent reward cannot be above 100.")
    for _ in range(5):
        code = "".join(secrets.choice(_ALPHABET) for _ in range(8))
        try:
            with transaction.atomic():
                row = ReferralCode.objects.create(
                    company=company,
                    referrer_customer=referrer_customer,
                    referrer_user=referrer_user,
                    code=code,
                    reward_type=reward_type,
                    reward_value=value,
                    created_by=user,
                    updated_by=user,
                )
        except IntegrityError:
            continue
        log_flag_event(company, "ENABLE_REFERRALS", "referral_code_issued", code_id=row.id)
        return row
    raise BusinessRuleError("Could not allocate a referral code, try again.")


def resolve_referral_code(company, raw: str):
    text = (raw or "").strip().upper()
    if not text:
        return None
    if not flag_enabled(company, "ENABLE_CRM") or not flag_enabled(company, "ENABLE_REFERRALS"):
        return None
    row = ReferralCode.objects.filter(company=company, code=text, active=True).first()
    if row is None:
        logger.info("referral_code_ignored tenant_id=%s", getattr(company, "id", None))
    return row


def resolve_campaign(company, raw, *, quiet: bool):
    if raw in (None, ""):
        return None
    from .models import Campaign

    try:
        campaign_id = int(raw)
    except (TypeError, ValueError):
        campaign_id = None
    campaign = None if campaign_id is None else Campaign.objects.filter(company=company, pk=campaign_id).first()
    if campaign is None:
        if quiet:
            logger.info("campaign_ignored tenant_id=%s", getattr(company, "id", None))
            return None
        raise BusinessRuleError("Campaign was not found.")
    return campaign


def _customer_identity_signals(customer) -> dict:
    """Best-effort identity fingerprint for a `masters.Customer` row."""
    if customer is None:
        return {"id": None, "phone": "", "email": "", "gstin": ""}
    return {
        "id": customer.id,
        "phone": _canon_phone(getattr(customer, "phone", "") or ""),
        "email": (getattr(customer, "email", "") or "").strip().lower(),
        "gstin": (getattr(customer, "gstin", "") or "").strip().upper(),
    }


def _employee_identity_signals(referrer_user) -> dict:
    """Best-effort identity fingerprint for an employee (`accounts.CompanyUser`)
    referrer.

    There is no `CompanyUser` <-> `Customer` link anywhere in this schema (an
    employee referring a customer is not itself a customer record), so a
    customer-id comparison is not possible for this branch. The judgment call
    here: fall back to the employee's own login identity — `accounts.User`
    already carries a unique `email` and a canonicalizable `phone` — as the
    best available proxy. This only catches the case where an employee
    refers "a customer" who is really their own contact details entered as
    the lead/customer (e.g. to launder a reward through a fake customer
    record); it cannot catch an employee referring a *different*, unrelated
    customer record that happens to belong to them in real life but has no
    shared phone/email on file — that is out of reach without a real
    employee-to-customer link, which does not exist in v1.
    """
    if referrer_user is None:
        return {"id": None, "phone": "", "email": "", "gstin": ""}
    user = getattr(referrer_user, "user", None)
    return {
        "id": None,
        "phone": _canon_phone(getattr(user, "phone", "") or ""),
        "email": (getattr(user, "email", "") or "").strip().lower(),
        "gstin": "",
    }


def _is_self_referral(referrer_signals: dict, referee_signals: dict) -> bool:
    if referrer_signals["id"] is not None and referrer_signals["id"] == referee_signals["id"]:
        return True
    if referrer_signals["phone"] and referrer_signals["phone"] == referee_signals["phone"]:
        return True
    if referrer_signals["email"] and referrer_signals["email"] == referee_signals["email"]:
        return True
    if referrer_signals["gstin"] and referrer_signals["gstin"] == referee_signals["gstin"]:
        return True
    return False


def _referral_self_check(code, referee_customer, lead=None) -> bool:
    """True when `code`'s referrer and the won deal look like the same person."""
    if referee_customer is None:
        if lead is None:
            return False
        referee_signals = {
            "id": None,
            "phone": _canon_phone(getattr(lead, "phone", "") or ""),
            "email": (getattr(lead, "email", "") or "").strip().lower(),
            "gstin": "",
        }
    else:
        referee_signals = _customer_identity_signals(referee_customer)
    if code.referrer_customer_id:
        return _is_self_referral(_customer_identity_signals(code.referrer_customer), referee_signals)
    if code.referrer_user_id:
        return _is_self_referral(_employee_identity_signals(code.referrer_user), referee_signals)
    return False


def reward_amount_for(reward_type, reward_value, base) -> Decimal:
    """Paisa-accurate reward. Flat and percent both keep two decimal places."""
    from .models import ReferralCode

    value = Decimal(str(reward_value or 0))
    if reward_type == ReferralCode.RewardType.PERCENT:
        return (Decimal(str(base or 0)) * value / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def evaluate_referral_reward(opportunity):
    lead = opportunity.lead
    if lead is None or not lead.referral_code_id:
        return None
    if not flag_enabled(opportunity.company, "ENABLE_REFERRALS"):
        return None
    existing = ReferralReward.objects.filter(company=opportunity.company, opportunity=opportunity).first()
    if existing is not None:
        return existing
    code = lead.referral_code
    amount = reward_amount_for(code.reward_type, code.reward_value, opportunity.amount)
    is_self_referral = _referral_self_check(code, opportunity.customer, lead=lead)
    status = ReferralReward.Status.REJECTED if is_self_referral else ReferralReward.Status.PENDING
    try:
        with transaction.atomic():
            reward = ReferralReward.objects.create(
                company=opportunity.company,
                referral_code=code,
                lead=lead,
                opportunity=opportunity,
                reward_amount=amount,
                reward_status=status,
                rejection_reason="self_referral" if is_self_referral else "",
                created_by=opportunity.updated_by,
                updated_by=opportunity.updated_by,
            )
    except IntegrityError:
        # A concurrent WON transition for the same opportunity won the race
        # against the (company, opportunity) unique constraint.
        return ReferralReward.objects.get(company=opportunity.company, opportunity=opportunity)
    if is_self_referral:
        AuditService.log(
            action="referral_self_referral_blocked",
            company=opportunity.company,
            user=opportunity.updated_by,
            entity_type="ReferralReward",
            entity_id=reward.id,
            description=(
                "Referral reward auto-rejected: the referrer's identity matches "
                "the won opportunity's customer (self-referral)."
            ),
            metadata={
                "referral_code_id": code.id,
                "opportunity_id": opportunity.id,
                "reward_amount": str(amount),
            },
        )
        log_flag_event(
            opportunity.company,
            "ENABLE_REFERRALS",
            "referral_reward_blocked_self_referral",
            reward_id=reward.id,
            opportunity_id=opportunity.id,
        )
    return reward


def _draft_reward_credit_note(reward, user):
    """One draft credit note for the referrer, through the existing notes service.

    Completing the note is a separate call and is what changes the balance.
    """
    from sales.models import NoteReason, SalesCreditNote, SalesInvoice
    from sales.notes_services import SalesNotesService

    customer = reward.referral_code.referrer_customer or reward.opportunity.customer
    if customer is None:
        raise BusinessRuleError("This reward has no customer to credit.")
    invoice = (
        SalesInvoice.objects.filter(
            company=reward.company,
            customer=customer,
            status=SalesInvoice.Status.COMPLETED,
        )
        .order_by("-id")
        .first()
    )
    if invoice is None:
        raise BusinessRuleError(
            "Complete a sales invoice for this customer before marking the reward paid."
        )
    source = invoice.items.order_by("id").first()
    if source is None:
        raise BusinessRuleError("The sales invoice has no lines to credit.")
    qty = min(Decimal("1"), Decimal(source.quantity))
    if qty <= 0:
        raise BusinessRuleError("The sales invoice line has no quantity left to credit.")
    unit_price = (Decimal(str(reward.reward_amount)) / qty).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP,
    )
    note = SalesCreditNote.objects.create(
        company=reward.company,
        customer=customer,
        sales_invoice=invoice,
        reason=NoteReason.OTHERS,
        notes=f"Referral reward {reward.pk}",
        filing_party_gstin=invoice.filing_party_gstin or (invoice.customer.gstin or ""),
        filing_place_of_supply=invoice.filing_place_of_supply or (invoice.customer.state or ""),
        company_gstin=invoice.company_gstin,
        created_by=user,
        updated_by=user,
    )
    SalesNotesService.set_credit_note_items(
        note,
        [{
            "product": source.product_id,
            "source_item": source.id,
            "quantity": str(qty),
            "unit_price": str(unit_price),
            "gst_rate": str(source.gst_rate),
        }],
        user,
    )
    return note


def mark_reward_paid(reward, user):
    """Draft one credit note and mark the reward paid.

    A later call returns the note already stored on the reward. Completing
    the note adjusts the customer balance. This does not send cash.
    """
    with transaction.atomic():
        reward = ReferralReward.objects.select_for_update().get(pk=reward.pk)
        if reward.credit_note_id:
            return reward
        if reward.reward_status == ReferralReward.Status.REJECTED:
            raise BusinessRuleError("A rejected reward cannot be marked paid.")
        if reward.reward_status != ReferralReward.Status.APPROVED:
            raise BusinessRuleError("Only an approved reward can be marked paid.")
        note = _draft_reward_credit_note(reward, user)
        reward.credit_note = note
        reward.reward_status = ReferralReward.Status.PAID
        reward.paid_at = timezone.now()
        reward.updated_by = user
        reward.save(update_fields=[
            "credit_note", "reward_status", "paid_at", "updated_by", "updated_at",
        ])
    AuditService.log(
        action="referral_reward_marked_paid",
        company=reward.company,
        user=user,
        entity_type="ReferralReward",
        entity_id=reward.pk,
        metadata={
            "reward_amount": str(reward.reward_amount),
            "credit_note_id": reward.credit_note_id,
        },
    )
    return reward


def referral_leaderboard(company) -> list[dict]:
    rows = (
        ReferralReward.objects.filter(
            company=company,
            reward_status__in=(ReferralReward.Status.APPROVED, ReferralReward.Status.PAID),
        )
        .values(
            "referral_code_id",
            "referral_code__referrer_customer_id",
            "referral_code__referrer_user_id",
            "referral_code__code",
        )
        .annotate(total=Sum("reward_amount"))
        .order_by("-total", "referral_code_id")
    )
    out = []
    for row in rows:
        if row["referral_code__referrer_customer_id"]:
            referrer_type = "customer"
            referrer_id = row["referral_code__referrer_customer_id"]
        else:
            referrer_type = "employee"
            referrer_id = row["referral_code__referrer_user_id"]
        out.append({
            "referral_code": row["referral_code_id"],
            "code": row["referral_code__code"],
            "referrer_type": referrer_type,
            "referrer_id": referrer_id,
            "approved_total": str(row["total"] or 0),
        })
    return out
