"""SET-23: in-app alerts for Settings problems that nobody would otherwise notice.

Licence expiry (30, 7 and 0 days), a failed automatic backup, a payment gateway that has gone quiet,
and a plan limit about to be reached. Each alert goes to the company's owners once: the message
carries a marker such as ``[lic:12:7]`` and an alert whose marker already exists is not sent again.
A daily Celery task runs ``run_settings_alerts``; a failed backup is raised at the moment it fails.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from core.models import Notification

logger = logging.getLogger(__name__)

LICENCE_THRESHOLDS = (30, 7, 0)
GATEWAY_SILENCE_DAYS = 7
PLAN_WARN_RATIO = 0.9


def _owners(company):
    from accounts.models import CompanyUser

    return list(
        CompanyUser.objects.filter(company=company, is_active=True, role=CompanyUser.Role.OWNER).select_related("user")
    )


def notify_owners(company, subject: str, body: str, marker: str) -> int:
    """Send once per marker. Returns how many owners were told this time."""
    from core.services.notifications import NotificationService

    text = f"{body} [{marker}]"
    sent = 0
    for membership in _owners(company):
        recipient = membership.user.email or str(membership.user_id)
        if Notification.objects.filter(company=company, recipient=recipient, body__contains=f"[{marker}]").exists():
            continue
        try:
            NotificationService.send(
                company=company,
                channel=Notification.Channel.IN_APP,
                recipient=recipient,
                subject=subject,
                body=text,
                user=membership.user,
            )
            sent += 1
        except Exception:  # noqa: BLE001 - one failed alert must not stop the rest
            logger.exception("settings alert failed company=%s marker=%s", company.pk, marker)
    return sent


def _licence_alerts(company, today) -> int:
    from accounts.models import CompanyStatutoryLicence

    sent = 0
    for lic in CompanyStatutoryLicence.objects.filter(company=company, is_active=True, valid_upto__isnull=False):
        days_left = (lic.valid_upto - today).days
        reached = [t for t in LICENCE_THRESHOLDS if days_left <= t]
        if not reached:
            continue
        threshold = min(reached)
        if threshold == 0:
            subject, body = "Licence expired", f"Licence {lic.licence_number} expired on {lic.valid_upto:%d %b %Y}. Add the renewal in Settings, Statutory licences."
        else:
            subject = f"Licence expires in {threshold} days"
            body = f"Licence {lic.licence_number} is valid until {lic.valid_upto:%d %b %Y}. Add the renewal in Settings, Statutory licences."
        sent += notify_owners(company, subject, body, f"lic:{lic.pk}:{threshold}")
    return sent


def gateway_is_quiet(company) -> bool:
    """Payment links were made recently with accepted keys, yet no payment notification has come back."""
    from payments.gateway import decrypt_gateway_credentials, keys_accepted_for
    from payments.models import PaymentLink, ProcessedWebhookEvent

    if not company.payment_gateway_credentials_encrypted:
        return False
    provider = company.payment_gateway_provider or "razorpay"
    if provider == "sandbox":
        return False
    creds = decrypt_gateway_credentials(company.payment_gateway_credentials_encrypted)
    if not keys_accepted_for(creds, provider):
        return False
    since = timezone.now() - timedelta(days=GATEWAY_SILENCE_DAYS)
    if not PaymentLink.objects.filter(company=company, created_at__gte=since).exists():
        return False
    return not ProcessedWebhookEvent.objects.filter(company=company, created_at__gte=since).exists()


def plan_pressure(company) -> list[str]:
    """Names of the plan limits that are at 90% or more."""
    from billing.quotas import usage_snapshot

    snapshot = usage_snapshot(company)
    return [
        metric
        for metric in ("seats", "completes", "storage_bytes")
        if int(snapshot[metric]["limit"] or 0) > 0
        and int(snapshot[metric]["used"] or 0) >= int(snapshot[metric]["limit"]) * PLAN_WARN_RATIO
    ]


def _gateway_alerts(company, today) -> int:
    if not gateway_is_quiet(company):
        return 0
    provider = company.payment_gateway_provider or "razorpay"
    year, week, _ = today.isocalendar()
    return notify_owners(
        company,
        "Payment notifications have gone quiet",
        f"Payment links were made in the last {GATEWAY_SILENCE_DAYS} days but no payment notification came back from "
        f"{provider.capitalize()}. Check the webhook address and secret in Settings, Payment gateway.",
        f"gw-silence:{year}-{week}",
    )


def _plan_alerts(company, today) -> int:
    from billing.quotas import usage_snapshot

    sent = 0
    snapshot = usage_snapshot(company)
    labels = {"seats": "users", "completes": "bills this month", "storage_bytes": "storage"}
    for metric, label in labels.items():
        limit = int(snapshot[metric]["limit"] or 0)
        used = int(snapshot[metric]["used"] or 0)
        if limit <= 0 or used < limit * PLAN_WARN_RATIO:
            continue
        level = 100 if used >= limit else 90
        sent += notify_owners(
            company,
            "Plan limit reached" if level == 100 else "Plan limit close",
            f"Your plan allows {limit} {label} and you are using {used}. See Settings, Billing.",
            f"plan:{metric}:{today:%Y-%m}:{level}",
        )
    return sent


def run_settings_alerts(company, today=None) -> int:
    today = today or timezone.localdate()
    total = 0
    for step in (_licence_alerts, _gateway_alerts, _plan_alerts):
        try:
            total += step(company, today)
        except Exception:  # noqa: BLE001
            logger.exception("settings alerts step %s failed company=%s", step.__name__, company.pk)
    return total
