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
    fetch_razorpay_paid_charges,
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
    invoiced = 0
    for sub in qs:
        sid = (sub.razorpay_subscription_id or "").strip()
        if not sid:
            continue
        checked += 1
        drifted = _reconcile_one(sub, sid, live_status=sub.status)
        if drifted:
            mismatches += 1
        invoiced += _invoice_missed_charges(sub, sid)

    # A deferred plan switch (B9-005) parks its new Razorpay subscription id
    # in pending_razorpay_subscription_id rather than the live id, so it's
    # invisible to the sweep above. Without this, a lost/delayed webhook for
    # that pending subscription has no recon fallback to promote it once it
    # goes active.
    pending_qs = (
        Subscription.objects.exclude(pending_razorpay_subscription_id="")
        .select_related("company")
        .order_by("pk")
    )
    for sub in pending_qs:
        sid = (sub.pending_razorpay_subscription_id or "").strip()
        if not sid:
            continue
        checked += 1
        # apply_razorpay_subscription_status only acts on a pending id once
        # it reports ACTIVE (any other status is not yet a confirmed switch
        # and is a no-op there) -- only that transition is worth recon acting
        # on, otherwise every sweep would "correct" (and audit-log) the same
        # still-pending subscription over and over for no actual change.
        drifted = _reconcile_one(sub, sid, only_when_mapped=Subscription.Status.ACTIVE)
        if drifted:
            mismatches += 1
    return {"skipped": False, "checked": checked, "mismatches": mismatches, "invoiced": invoiced}


def _reconcile_one(sub: Subscription, sid: str, *, live_status=None, only_when_mapped=None) -> bool:
    """Fetch remote status for one Razorpay subscription id and correct local
    drift. Returns True if a mismatch was found (corrected or parked)."""
    try:
        remote = fetch_razorpay_subscription(sid)
    except Exception as exc:  # noqa: BLE001 — park, keep sweeping
        _park(sub, error=str(exc), remote_status="", payload={"id": sid})
        return True
    if not remote:
        _park(sub, error="empty Razorpay payload", remote_status="", payload={})
        return True
    remote_status = str(remote.get("status") or "")
    mapped = map_razorpay_status(remote_status)
    if mapped is None:
        return False
    if only_when_mapped is not None:
        if mapped != only_when_mapped:
            return False
    elif mapped == live_status:
        return False
    local_status = sub.status
    try:
        apply_razorpay_subscription_status(
            razorpay_subscription_id=sid,
            rzp_status=remote_status,
            current_end=remote.get("current_end") or remote.get("current_end_at"),
        )
    except Exception as exc:  # noqa: BLE001
        _park(sub, error=str(exc), remote_status=remote_status, payload=remote)
        return True
    # The drift was found AND successfully corrected -- there is nothing
    # left to replay, so this must not go to the DLQ (that queue is a
    # "needs action" surface; parking every self-healed mismatch there
    # buries genuine unresolved failures under routine corrections). The
    # audit log below is the durable record of what changed.
    AuditService.log(
        action="billing.recon",
        company=sub.company,
        entity_type="Subscription",
        entity_id=sub.pk,
        description="Razorpay subscription status drifted from local; corrected.",
        metadata={"local": local_status, "remote": remote_status, "mapped": mapped},
    )
    return True


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


# A lost webhook is caught within days; anything older is history from before Bizboard issued its
# own GST invoices and must not be invoiced now, dated today (wrong period on GSTR-1).
MISSED_CHARGE_WINDOW_DAYS = 35


def _missed_charge_cutoff():
    """The earliest charge time the sweep may invoice: the window, and never before
    ``PLATFORM_GST_INVOICES_FROM`` (the go-live date, ISO) when that is set."""
    from datetime import datetime, time, timedelta

    from django.utils import timezone

    cutoff = timezone.now() - timedelta(days=MISSED_CHARGE_WINDOW_DAYS)
    raw = (getattr(settings, "PLATFORM_GST_INVOICES_FROM", "") or "").strip()
    if raw:
        try:
            go_live = timezone.make_aware(datetime.combine(datetime.fromisoformat(raw).date(), time.min))
        except ValueError:
            logger.warning("PLATFORM_GST_INVOICES_FROM=%r is not an ISO date; ignored", raw)
        else:
            cutoff = max(cutoff, go_live)
    return cutoff


def _invoice_missed_charges(sub: Subscription, sid: str) -> int:
    """WP-BL2: issue the GST invoice for any recent paid Razorpay charge that has none (a lost
    ``subscription.charged`` webhook). Returns how many were issued."""
    from datetime import timedelta

    from django.utils import timezone

    from billing.models import PlatformGstInvoice
    from billing.platform_gst import issue_platform_gst_invoice

    recently_live = sub.status in (Subscription.Status.ACTIVE, Subscription.Status.PAST_DUE) or (
        sub.updated_at and sub.updated_at >= timezone.now() - timedelta(days=MISSED_CHARGE_WINDOW_DAYS)
    )
    if not recently_live:
        return 0  # a long-cancelled subscription has no charge the webhook can still have missed
    try:
        charges = fetch_razorpay_paid_charges(sid)
    except Exception as exc:  # noqa: BLE001 - park, keep sweeping
        _park(sub, error=f"charges fetch: {exc}", remote_status="charges", payload={"id": sid})
        return 0
    cutoff_ts = int(_missed_charge_cutoff().timestamp())
    charges = [c for c in charges if int(c.get("paid_at") or 0) >= cutoff_ts]
    if not charges:
        return 0
    have = set(
        PlatformGstInvoice.objects.filter(
            company=sub.company, provider="razorpay", capture_id__in=[c["payment_id"] for c in charges],
        ).values_list("capture_id", flat=True)
    )
    issued = 0
    for charge in charges:
        if charge["payment_id"] in have:
            continue
        try:
            issue_platform_gst_invoice(
                sub.company, provider="razorpay", capture_id=charge["payment_id"], amount=charge["amount"],
            )
        except Exception as exc:  # noqa: BLE001 - park this charge, keep sweeping the rest
            _park(sub, error=f"invoice {charge['payment_id']}: {exc}", remote_status="invoice",
                  payload={"id": sid, "payment_id": charge["payment_id"]})
            continue
        issued += 1
    if issued:
        AuditService.log(
            action="billing.recon_invoice",
            company=sub.company,
            entity_type="Subscription",
            entity_id=sub.pk,
            description=f"Issued {issued} GST invoice(s) for Razorpay charges with no invoice.",
            metadata={"subscription": sid},
        )
    return issued
