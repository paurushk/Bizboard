"""D-19 (2026-10-25, BB-139): one Bizboard customer refers another business.

Behind the company flag ENABLE_SAAS_REFERRALS (off). The reward is recorded only: qualified
referrals are listed in Django admin and Bizboard staff settle them by hand (no credit, no
discount, nothing touches money).

Flow:
1. The referrer's owner opens Settings > Billing; ``link_for`` makes the company's link.
2. A new business signs up (password or Google) with ``?ref=<code>``. ``attribute_signup`` runs
   inside ``create_owner_account`` and records a SIGNED_UP event for the referrer.
3. ``qualify_referrals`` (daily) records QUALIFIED once the referred company is ACTIVE on a paid
   plan, and voids the referral if it turns out to be the same business (same GSTIN).

Tenancy: events belong to the referrer, but steps 2 and 3 run as the referred company (or as no
company, during sign-up). The code lookup reads two ids under a narrow ``rls_bypass``; every write
goes through ``record_event``, which writes inside ``company_scope(referrer)``.
"""

from __future__ import annotations

import logging
import secrets

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

FLAG = "ENABLE_SAAS_REFERRALS"
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I/L
CODE_LENGTH = 8
# Mail providers anyone can sign up with: sharing one says nothing about being the same business.
PUBLIC_MAIL_DOMAINS = frozenset({
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.in", "outlook.com", "hotmail.com", "live.com",
    "icloud.com", "me.com", "rediffmail.com", "proton.me", "protonmail.com", "zoho.com", "zohomail.in",
    "aol.com", "gmx.com", "yandex.com",
})


def enabled(company) -> bool:
    from core.services.feature_flags import flag_enabled

    return bool(company) and company.erased_at is None and flag_enabled(company, FLAG)


def normalise(code: str) -> str:
    return "".join(ch for ch in str(code or "").upper() if ch.isalnum())[:16]


def _new_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(CODE_LENGTH))


def link_for(company, user=None):
    """The company's referral link, made on first use. Call in the company's own request context."""
    from .models import ReferralLink

    link = ReferralLink.objects.filter(company=company).first()
    if link:
        return link
    for _ in range(5):
        try:
            with transaction.atomic():
                return ReferralLink.objects.create(company=company, code=_new_code(), created_by=user, updated_by=user)
        except IntegrityError:
            existing = ReferralLink.objects.filter(company=company).first()
            if existing:
                return existing  # a concurrent first view made it
    raise RuntimeError("could not allocate a referral code")


def summary(company) -> dict:
    from .models import ReferralEvent

    live = ReferralEvent.objects.filter(company=company, voided_at__isnull=True)
    return {
        "signed_up": live.filter(kind=ReferralEvent.Kind.SIGNED_UP).count(),
        "qualified": live.filter(kind=ReferralEvent.Kind.QUALIFIED).count(),
    }


def record_event(*, link_id: int, referrer_id: int, referred_company, kind: str, **fields):
    """The one place a referral event is written: inside the referrer's RLS scope."""
    from core.rls import company_scope

    from .models import ReferralEvent

    with company_scope(referrer_id), transaction.atomic():
        return ReferralEvent.objects.create(
            company_id=referrer_id, link_id=link_id, referred_company=referred_company, kind=kind, **fields,
        )


def _domain(email: str) -> str:
    return (email or "").rsplit("@", 1)[-1].strip().lower()


def _same_business(referrer, new_company, new_owner_email: str) -> str:
    """Why this sign-up cannot be the referrer's referral, or "" if it can."""
    from accounts.models import CompanyUser

    if referrer.pk == new_company.pk:
        return "self"
    g1, g2 = (referrer.gstin or "").strip().upper(), (new_company.gstin or "").strip().upper()
    if g1 and g1 == g2:
        return "same GSTIN"
    domain = _domain(new_owner_email)
    if domain and domain not in PUBLIC_MAIL_DOMAINS:
        owner_domains = {
            _domain(e) for e in CompanyUser.objects.filter(company=referrer).values_list("user__email", flat=True)
        }
        if domain in owner_domains:
            return "same email domain"
    return ""


def attribute_signup(new_company, code: str, *, owner_email: str = "") -> bool:
    """Record that ``new_company`` signed up with ``code``. Never raises: a bad or unknown code, or
    any error here, must not stop the sign-up."""
    code = normalise(code)
    if not code:
        return False
    try:
        with transaction.atomic():
            return _attribute(new_company, code, owner_email)
    except Exception:  # noqa: BLE001 - sign-up must succeed whatever happens to the referral
        logger.exception("referral attribution failed company=%s", new_company.pk)
        return False


def _attribute(new_company, code: str, owner_email: str) -> bool:
    from accounts.models import Company
    from core.rls import company_scope, rls_bypass

    from .models import ReferralEvent, ReferralLink

    with rls_bypass():  # narrow read: which company owns this code (sign-up has no tenant yet)
        found = ReferralLink.objects.filter(code=code, is_active=True).values("id", "company_id").first()
    if not found:
        return False
    referrer = Company.objects.filter(pk=found["company_id"]).first()
    if not enabled(referrer):
        return False
    reason = _same_business(referrer, new_company, owner_email)
    if reason:
        logger.info("referral not attributed company=%s code=%s: %s", new_company.pk, code, reason)
        return False
    cap = int(getattr(settings, "SAAS_REFERRAL_DAILY_CAP", 20))
    since = timezone.now() - timezone.timedelta(days=1)
    with company_scope(referrer.pk):
        recent = ReferralEvent.objects.filter(
            link_id=found["id"], kind=ReferralEvent.Kind.SIGNED_UP, created_at__gte=since,
        ).count()
    if recent >= cap:
        logger.warning("referral daily cap reached link=%s", found["id"])
        return False
    record_event(link_id=found["id"], referrer_id=referrer.pk, referred_company=new_company,
                 kind=ReferralEvent.Kind.SIGNED_UP)
    return True


def _is_paying(company, now) -> bool:
    sub = getattr(company, "saas_subscription", None)
    return bool(
        sub and sub.status == sub.Status.ACTIVE and sub.plan.price_paise > 0
        and (sub.current_period_end is None or sub.current_period_end > now)
    )


def qualify_referrals(*, now=None) -> dict:
    """Daily: QUALIFIED for referred companies now paying; void same-business referrals."""
    from core.rls import rls_bypass

    from .models import ReferralEvent

    now = now or timezone.now()
    counts = {"qualified": 0, "voided": 0}
    with rls_bypass():
        pending = (
            ReferralEvent.objects.filter(
                kind=ReferralEvent.Kind.SIGNED_UP, voided_at__isnull=True, referred_company__isnull=False,
            )
            .exclude(referred_company__in=ReferralEvent.objects.filter(kind=ReferralEvent.Kind.QUALIFIED)
                     .values("referred_company"))
            .select_related("company", "referred_company", "referred_company__saas_subscription__plan")
        )
        for event in pending:
            referred = event.referred_company
            reason = _same_business(event.company, referred, "")
            if reason:
                event.voided_at, event.void_reason = now, f"Same business ({reason})"
                event.save(update_fields=["voided_at", "void_reason", "updated_at"])
                counts["voided"] += 1
                continue
            if not _is_paying(referred, now):
                continue
            try:
                record_event(link_id=event.link_id, referrer_id=event.company_id, referred_company=referred,
                             kind=ReferralEvent.Kind.QUALIFIED)
                counts["qualified"] += 1
            except IntegrityError:
                pass  # recorded by a concurrent run
    return counts
