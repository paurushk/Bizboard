"""8.6 — SaaS billing recon vs Razorpay subscriptions.

Collections recon (payments.services.reconcile_gateway_captures) is a different
pipeline. This module only compares local Subscription rows that have a
razorpay_subscription_id against GET /v1/subscriptions/{id}.
"""

from __future__ import annotations

import logging

from django.conf import settings

from billing.models import Subscription
from billing.services import (
    apply_razorpay_subscription_status,
    fetch_razorpay_subscription,
    map_razorpay_status,
    park_dead_letter,
)
from core.services.audit import AuditService

logger = logging.getLogger(__name__)


def razorpay_keys_configured() -> bool:
    key = (getattr(settings, "RAZORPAY_KEY_ID", "") or "").strip()
    secret = (getattr(settings, "RAZORPAY_KEY_SECRET", "") or "").strip()
    return bool(key and secret)


def reconcile_saas_subscriptions() -> dict:
    """Fetch remote Razorpay status; apply mapping; park mismatches on DLQ.

    Skips entirely when Razorpay keys are unset (local/CI). Never calls AR recon.
    """
    if not razorpay_keys_configured():
        return {"skipped": True, "reason": "no_razorpay_keys", "checked": 0, "mismatches": 0}
    env = (getattr(settings, "DJANGO_ENV", "") or "").lower()
    if env == "test" and not getattr(settings, "BILLING_RECON_IN_TESTS", False):
        return {"skipped": True, "reason": "test_env", "checked": 0, "mismatches": 0}

    checked = mismatches = 0
    qs = (
        Subscription.objects.exclude(razorpay_subscription_id="")
        .select_related("company")
        .order_by("pk")
    )
    for sub in qs:
        sid = (sub.razorpay_subscription_id or "").strip()
        if not sid:
            continue
        checked += 1
        try:
            remote = fetch_razorpay_subscription(sid)
        except Exception as exc:  # noqa: BLE001 — park, keep sweeping
            _park(sub, error=str(exc), remote_status="", payload={"id": sid})
            mismatches += 1
            continue
        if not remote:
            _park(sub, error="empty Razorpay payload", remote_status="", payload={})
            mismatches += 1
            continue
        remote_status = str(remote.get("status") or "")
        mapped = map_razorpay_status(remote_status)
        if mapped is None:
            continue
        if mapped == sub.status:
            continue
        local_status = sub.status
        try:
            apply_razorpay_subscription_status(
                razorpay_subscription_id=sid,
                rzp_status=remote_status,
                current_end=remote.get("current_end") or remote.get("current_end_at"),
            )
        except Exception as exc:  # noqa: BLE001
            _park(sub, error=str(exc), remote_status=remote_status, payload=remote)
            mismatches += 1
            continue
        # The drift was found AND successfully corrected -- there is nothing
        # left to replay, so this must not go to the DLQ (that queue is a
        # "needs action" surface; parking every self-healed mismatch there
        # buries genuine unresolved failures under routine corrections). The
        # audit log below is the durable record of what changed.
        mismatches += 1
        AuditService.log(
            action="billing.recon",
            company=sub.company,
            entity_type="Subscription",
            entity_id=sub.pk,
            description="Razorpay subscription status drifted from local; corrected.",
            metadata={"local": local_status, "remote": remote_status, "mapped": mapped},
        )
    return {"skipped": False, "checked": checked, "mismatches": mismatches}


def _park(sub: Subscription, *, error: str, remote_status: str, payload: dict) -> None:
    # Dedup is enforced atomically by billing_dlq_uniq_pending_provider_event
    # (park_dead_letter catches the IntegrityError and returns the existing
    # PENDING row) -- no separate check-then-create race here.
    event_id = f"recon:{sub.pk}:{remote_status or 'fetch'}"[:128]
    park_dead_letter(
        provider="billing_recon",
        event_id=event_id,
        payload=payload if isinstance(payload, dict) else {},
        error=(error or "")[:4000],
        company=sub.company,
    )
    logger.warning("SaaS billing recon parked company=%s sub=%s %s", sub.company_id, sub.pk, error)
