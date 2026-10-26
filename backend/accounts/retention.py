"""D-13 (2026-10-25): delete a read-only workspace's data after the owner's retention period.

A workspace is read-only when it has no paid or trial access (billing.services.company_writes_blocked).
The daily task records when that started (Company.read_only_since) and clears it on renewal. The
owners are told 30 and 7 days before the deletion date, by email and in the app, and can export at
any time. On the date the company is erased in tombstone mode: operational data goes, the
anonymised statutory tax documents stay for the 8-year GST window (accounts/erasure.py).

Deletion runs only when settings.DATA_RETENTION_ENFORCE is on (off until counsel confirms the
policy); until then the task warns and logs what it would delete.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

WARN_DAYS = (30, 7)


def deletion_due_at(company):
    """When this workspace's data is deleted, or None while it is not read-only."""
    if company.read_only_since is None:
        return None
    return company.read_only_since + timedelta(days=company.data_retention_days)


def _warn_owners(company, days_left: int, due) -> int:
    from accounts.settings_alerts import _owners
    from core.models import Notification
    from core.services.notifications import NotificationService

    marker = f"retention:{company.pk}:{company.read_only_since:%Y%m%d}:{days_left}"
    subject = "Your Bizboard data will be deleted soon"
    body = (
        f"{company.name} has been read-only since {company.read_only_since:%d %b %Y}. Its data will be "
        f"deleted on {due:%d %b %Y} ({company.data_retention_days} days after it became read-only). "
        "Renew your plan to keep it, or download an export from Settings > Backup / Export before then. "
        f"Tax documents are kept in anonymised form as the law requires. [{marker}]"
    )
    sent = 0
    for membership in _owners(company):
        recipient_email = membership.user.email
        for channel, recipient in (
            (Notification.Channel.IN_APP, recipient_email or str(membership.user_id)),
            (Notification.Channel.EMAIL, recipient_email),
        ):
            if not recipient:
                continue
            if Notification.objects.filter(
                company=company, channel=channel, recipient=recipient, body__contains=f"[{marker}]",
            ).exists():
                continue
            try:
                NotificationService.send(
                    company=company, channel=channel, recipient=recipient, subject=subject, body=body,
                    user=membership.user,
                )
                sent += 1
            except Exception:  # noqa: BLE001 - one failed notice must not stop the rest
                logger.exception("retention warning failed company=%s channel=%s", company.pk, channel)
    return sent


def apply_retention(company, *, now=None) -> str:
    """One company's daily step. Returns what happened: "active", "started", "waiting", "warned",
    "would_erase" (enforcement off) or "erased"."""
    from billing.services import company_writes_blocked

    now = now or timezone.now()
    if company.erased_at is not None or company.is_sandbox:
        return "active"
    if not company_writes_blocked(company):
        if company.read_only_since is not None:
            company.read_only_since = None
            company.save(update_fields=["read_only_since"])
        return "active"
    if company.read_only_since is None:
        company.read_only_since = now
        company.save(update_fields=["read_only_since"])
        return "started"
    due = deletion_due_at(company)
    if now >= due:
        if not getattr(settings, "DATA_RETENTION_ENFORCE", False):
            logger.info(
                "retention: company=%s read-only since %s, past its %s-day period; would erase "
                "(DATA_RETENTION_ENFORCE is off)",
                company.pk, company.read_only_since.date(), company.data_retention_days,
            )
            return "would_erase"
        from accounts.erasure import erase_company

        erase_company(
            company, mode="tombstone", requested_by_email="retention@system",
            reason=f"Read-only for {company.data_retention_days} days (data retention, D-13)",
        )
        logger.warning("retention: erased company=%s after %s days read-only", company.pk, company.data_retention_days)
        return "erased"
    days_left = (due - now).days
    # The tightest warning reached so far (7 inside a week, else 30 inside a month), once each.
    reached = [t for t in WARN_DAYS if days_left <= t]
    if not reached:
        return "waiting"
    return "warned" if _warn_owners(company, min(reached), due) else "waiting"
