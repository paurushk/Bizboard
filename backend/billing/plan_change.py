"""WP-BL3: plan changes for a paying subscriber (Q6: upgrade now with a one-time prorated charge;
downgrade at period end).

Built on the existing switch (``start_or_update_subscription``): the new plan's Razorpay
subscription is created to start when the paid period ends, parked in
``pending_razorpay_subscription_id``, and the old one is cancelled once the new one is active.
On top of that:

- **Upgrade** (higher price): the new plan's modules and limits apply at once (``effective_plan``).
  The difference for the rest of the current period — seconds left × (new − old monthly price) /
  30 days — is charged once with a Razorpay payment link; its ``payment_link.paid`` webhook issues
  the GST invoice (WP-BL2). A UPI Autopay mandate is for a fixed amount, so the new subscription
  needs its own mandate approval (its ``short_url``); until then the old mandate keeps renewing
  and the upgrade stays on through the period. If the prorated charge is not paid within
  ``GRACE`` the upgrade is reverted and the pending subscription cancelled (daily task).
- **Downgrade**: takes effect at period end (``pending_plan``); refused while current use is over
  the new plan's limits, saying what to remove first.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessRuleError

logger = logging.getLogger(__name__)

GRACE = timedelta(days=3)
PERIOD = timedelta(days=30)


def effective_plan(sub):
    """The plan whose modules and limits apply now."""
    if sub is None:
        return None
    up = getattr(sub, "upgrade_plan", None)
    if up is not None and sub.upgrade_plan_id:
        if sub.proration_paid_at or (sub.upgrade_grace_until and sub.upgrade_grace_until > timezone.now()):
            return up
    return sub.plan


def proration_paise(*, old_price: int, new_price: int, period_end, now=None) -> int:
    now = now or timezone.now()
    if not period_end or period_end <= now or new_price <= old_price:
        return 0
    left = min((period_end - now).total_seconds(), PERIOD.total_seconds())
    return int(round((new_price - old_price) * left / PERIOD.total_seconds()))


def check_downgrade(company, plan) -> None:
    """Refuse a downgrade below what the company already uses."""
    from .quotas import usage_snapshot

    usage = usage_snapshot(company, plan=plan)
    over = []
    seats = usage["seats"]
    if seats["limit"] and seats["used"] > seats["limit"]:
        over.append(f"remove {seats['used'] - seats['limit']} user(s) (the plan allows {seats['limit']})")
    storage = usage["storage_bytes"]
    if storage["limit"] and storage["used"] > storage["limit"]:
        over.append(f"free {round((storage['used'] - storage['limit']) / 1_048_576, 1)} MB of files")
    if over:
        raise BusinessRuleError(
            f"{plan.name} is smaller than what you use now. First " + " and ".join(over) + ".",
            code="DOWNGRADE_OVER_QUOTA",
        )


def _create_payment_link(company, *, amount_paise: int, description: str, notes: dict, expire_by) -> tuple[str, str]:
    """POST /v1/payment_links. Returns (id, short_url); a stub id without keys (local, tests)."""
    import base64
    import json
    from urllib.request import Request, urlopen

    key = (getattr(settings, "RAZORPAY_KEY_ID", "") or "").strip()
    secret = (getattr(settings, "RAZORPAY_KEY_SECRET", "") or "").strip()
    if not key or not secret:
        return f"stub_plink_{company.pk}_{int(timezone.now().timestamp())}", ""
    body = {
        "amount": int(amount_paise),
        "currency": "INR",
        "description": description[:255],
        "expire_by": int(expire_by.timestamp()),
        "reminder_enable": True,
        "notes": {k: str(v) for k, v in notes.items()},
    }
    email = getattr(company, "email", "") or ""
    if email:
        body["customer"] = {"email": email, "name": (company.name or "")[:50]}
        body["notify"] = {"email": True, "sms": False}
    req = Request(
        "https://api.razorpay.com/v1/payment_links",
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Basic " + base64.b64encode(f"{key}:{secret}".encode()).decode(),
        },
    )
    try:
        with urlopen(req, timeout=15) as resp:  # noqa: S310 — fixed Razorpay HTTPS URL
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise BusinessRuleError("Could not create the payment for the upgrade. Try again.") from exc
    return str(payload.get("id") or ""), str(payload.get("short_url") or "")


def start_upgrade(sub, plan, *, now=None) -> str:
    """Apply ``plan`` now and ask for the prorated difference. Returns the payment link URL."""
    now = now or timezone.now()
    amount = proration_paise(
        old_price=int(sub.plan.price_paise or 0), new_price=int(plan.price_paise or 0),
        period_end=sub.current_period_end, now=now,
    )
    sub.upgrade_plan = plan
    sub.upgrade_started_at = now
    sub.upgrade_grace_until = now + GRACE
    sub.proration_amount_paise = amount
    sub.proration_paid_at = None
    url = ""
    if amount > 0:
        link_id, url = _create_payment_link(
            sub.company, amount_paise=amount,
            description=f"Upgrade to {plan.name} for the rest of this billing period",
            notes={"kind": "proration", "company_id": sub.company_id, "plan": plan.slug},
            expire_by=now + GRACE,
        )
        sub.proration_link_id = link_id
    else:
        sub.proration_link_id = ""
        sub.proration_paid_at = now  # nothing to pay (e.g. last moments of the period)
    sub.save(update_fields=[
        "upgrade_plan", "upgrade_started_at", "upgrade_grace_until", "proration_amount_paise",
        "proration_link_id", "proration_paid_at", "updated_at",
    ])
    return url


def clear_upgrade(sub, update_fields: list[str] | None = None) -> None:
    """The new plan's own subscription is active (or the upgrade ended): drop the overlay."""
    sub.upgrade_plan = None
    sub.upgrade_started_at = None
    sub.upgrade_grace_until = None
    sub.proration_link_id = ""
    fields = ["upgrade_plan", "upgrade_started_at", "upgrade_grace_until", "proration_link_id"]
    if update_fields is not None:
        update_fields.extend(fields)
    else:
        sub.save(update_fields=[*fields, "updated_at"])


def handle_payment_link_event(payload: dict) -> dict:
    """``payment_link.paid``: mark the proration paid and issue its GST invoice (once)."""
    from core.rls import rls_bypass

    from .models import Subscription
    from .platform_gst import issue_platform_gst_invoice

    event = str(payload.get("event") or "")
    body = payload.get("payload") or {}
    link = ((body.get("payment_link") or {}).get("entity")) or {}
    payment = ((body.get("payment") or {}).get("entity")) or {}
    link_id = str(link.get("id") or "")
    if event != "payment_link.paid" or not link_id:
        return {"ok": True, "ignored": True}
    with rls_bypass():
        with transaction.atomic():
            sub = Subscription.objects.select_for_update().filter(proration_link_id=link_id).select_related("company").first()
            if sub is None:
                return {"ok": True, "ignored": True}
            if sub.proration_paid_at is None:
                sub.proration_paid_at = timezone.now()
                sub.save(update_fields=["proration_paid_at", "updated_at"])
        payment_id = str(payment.get("id") or "")
        paise = int(payment.get("amount") or link.get("amount_paid") or link.get("amount") or 0)
        if payment_id and paise > 0:
            from decimal import Decimal

            issue_platform_gst_invoice(sub.company, provider="razorpay", capture_id=payment_id,
                                       amount=Decimal(paise) / Decimal(100))
    return {"ok": True, "proration_paid": True}


def revert_unpaid_upgrades(now=None) -> int:
    """Daily: an upgrade whose prorated charge was not paid in time goes back to the old plan,
    and its pending subscription (which would renew at the higher price) is cancelled."""
    from core.rls import rls_bypass

    from .models import Subscription
    from .services import _cancel_razorpay_subscription

    now = now or timezone.now()
    n = 0
    with rls_bypass():
        due = Subscription.objects.filter(
            upgrade_plan__isnull=False, proration_paid_at__isnull=True, upgrade_grace_until__lte=now,
        ).select_related("company", "upgrade_plan")
        for sub in due:
            with transaction.atomic():
                sub = Subscription.objects.select_for_update().get(pk=sub.pk)
                if sub.proration_paid_at is not None or sub.upgrade_plan_id is None:
                    continue
                pending = (sub.pending_razorpay_subscription_id or "").strip()
                if pending and sub.pending_plan_id == sub.upgrade_plan_id:
                    _cancel_razorpay_subscription(pending, at_cycle_end=False)
                    sub.pending_razorpay_subscription_id = ""
                    sub.pending_plan = None
                fields: list[str] = []
                clear_upgrade(sub, fields)
                sub.save(update_fields=[*fields, "pending_razorpay_subscription_id", "pending_plan", "updated_at"])
            _notify_reverted(sub)
            n += 1
    return n


def _notify_reverted(sub) -> None:
    from core.models import Notification
    from core.services.notifications import NotificationService

    company = sub.company
    if getattr(company, "email", ""):
        NotificationService.send(
            company=company, channel=Notification.Channel.EMAIL, recipient=company.email,
            subject="Your plan upgrade was undone",
            body=("The payment for your plan upgrade was not received within 3 days, so your plan is back "
                  f"to {sub.plan.name}. Choose the plan again under Billing to retry."),
        )
