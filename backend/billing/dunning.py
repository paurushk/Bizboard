"""8.5 — SaaS subscription dunning. Must not call AR dunning in the payments app.

Cadence is PAST_DUE only. Notices are operational (pay to keep writes), not
legal collection copy. Email is best-effort; AuditEvent is the durable record.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from billing.models import Subscription
from core.services.audit import AuditService

logger = logging.getLogger(__name__)

# day-offset from current_period_end (or updated_at) → step. Step 3 is the last
# reminder before BILLING_PAST_DUE_GRACE_DAYS write-block (when grace > 0).
_STEPS = ((0, 1), (3, 2), (7, 3))


def _step_for_days(days: int) -> int:
    step = 1
    for threshold, candidate in _STEPS:
        if days >= threshold:
            step = candidate
    return step


def run_saas_dunning(*, now=None) -> dict:
    """Notify PAST_DUE SaaS subscribers. Never touches customer AR dunning."""
    now = now or timezone.now()
    sent = skipped = 0
    qs = (
        Subscription.objects.filter(status=Subscription.Status.PAST_DUE)
        .select_related("company", "plan")
        .order_by("pk")
    )
    for sub in qs:
        company = sub.company
        if company is None or getattr(company, "billing_override_active", False):
            skipped += 1
            continue
        if getattr(company, "erased_at", None):
            skipped += 1
            continue
        anchor = sub.current_period_end or sub.updated_at or now
        days = max(0, (now - anchor).days)
        step = _step_for_days(days)
        if (sub.last_dunning_step or 0) >= step:
            skipped += 1
            continue
        _notify(sub, step=step, days=days, now=now)
        sent += 1
    return {"sent": sent, "skipped": skipped}


def _notify(sub: Subscription, *, step: int, days: int, now) -> None:
    company = sub.company
    to_email = _owner_email(company)
    subject = "BizBoard subscription past due"
    body = (
        f"Company {company.name} (id={company.pk}) SaaS subscription is past due "
        f"(step {step}, {days} day(s) after period end). "
        "Complete payment to keep writes enabled. This is not a customer AR reminder."
    )
    if to_email:
        try:
            send_mail(
                subject,
                body,
                getattr(settings, "DEFAULT_FROM_EMAIL", "billing@bizboard.local"),
                [to_email],
                fail_silently=False,
            )
        except Exception:  # noqa: BLE001 — sweep must not die on SMTP
            logger.exception("SaaS dunning email failed company=%s", company.pk)
    AuditService.log(
        action="billing.dunning",
        company=company,
        entity_type="Subscription",
        entity_id=sub.pk,
        description=subject,
        metadata={"step": step, "days": days, "email": bool(to_email)},
    )
    sub.last_dunning_at = now
    sub.last_dunning_step = step
    sub.save(update_fields=["last_dunning_at", "last_dunning_step", "updated_at"])


def _owner_email(company) -> str:
    from accounts.models import CompanyUser

    row = (
        CompanyUser.objects.filter(company=company, role=CompanyUser.Role.OWNER)
        .select_related("user")
        .first()
    )
    if row is None or row.user is None:
        return ""
    return (row.user.email or "").strip()
