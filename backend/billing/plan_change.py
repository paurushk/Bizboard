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
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessRuleError

logger = logging.getLogger(__name__)

GRACE = timedelta(days=3)
PERIOD = timedelta(days=30)


def effective_plan(sub):
    """The plan whose modules and limits apply now.

    An upgrade overlay applies only until ``upgrade_grace_until``: 3 days for an unpaid prorated
    charge, and once paid, until the end of the period it was paid for (plus the grace). The new
    plan's own subscription takes over at the period end; if its mandate is never approved the
    overlay simply lapses instead of giving the higher plan for free forever.
    """
    if sub is None:
        return None
    up = getattr(sub, "upgrade_plan", None)
    until = getattr(sub, "upgrade_grace_until", None)
    if up is not None and sub.upgrade_plan_id and isinstance(until, datetime) and until > timezone.now():
        return up
    return sub.plan


def upgrade_in_progress(sub) -> bool:
    return bool(sub is not None and sub.upgrade_plan_id and sub.upgrade_grace_until
                and sub.upgrade_grace_until > timezone.now())


def _paid_until(sub, now):
    """How long a paid upgrade stays on: to the end of the period it covers, plus the grace."""
    end = sub.current_period_end if sub.current_period_end and sub.current_period_end > now else now
    return end + GRACE


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


def _razorpay_auth() -> str:
    import base64

    key = (getattr(settings, "RAZORPAY_KEY_ID", "") or "").strip()
    secret = (getattr(settings, "RAZORPAY_KEY_SECRET", "") or "").strip()
    if not key or not secret:
        return ""
    return "Basic " + base64.b64encode(f"{key}:{secret}".encode()).decode()


def _is_stub_link(link_id: str) -> bool:
    return not link_id or link_id.startswith("stub_plink_")


def _create_payment_link(company, *, amount_paise: int, description: str, notes: dict, expire_by) -> tuple[str, str]:
    """POST /v1/payment_links. Returns (id, short_url); a stub id without keys (local, tests)."""
    import json
    from urllib.request import Request, urlopen

    auth = _razorpay_auth()
    if not auth:
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
        headers={"Content-Type": "application/json", "Authorization": auth},
    )
    from core.circuit_breaker import call as circuit_call

    def _post():
        with urlopen(req, timeout=15) as resp:  # noqa: S310 — fixed Razorpay HTTPS URL
            return json.loads(resp.read().decode("utf-8"))

    try:
        payload = circuit_call("razorpay_subscriptions", _post, failure_threshold=5, cooldown_seconds=30)
    except Exception as exc:  # noqa: BLE001
        raise BusinessRuleError("Could not create the payment for the upgrade. Try again.") from exc
    return str(payload.get("id") or ""), str(payload.get("short_url") or "")


def _payment_link_status(link_id: str) -> str:
    """GET /v1/payment_links/{id} status ("paid", "created", "expired", ...). Raises on network
    errors so a caller deciding to revert can wait for the next run instead of guessing."""
    import json
    from urllib.request import Request, urlopen

    auth = _razorpay_auth()
    if not auth or _is_stub_link(link_id):
        return ""
    req = Request(f"https://api.razorpay.com/v1/payment_links/{link_id}", method="GET",
                  headers={"Authorization": auth})
    with urlopen(req, timeout=15) as resp:  # noqa: S310 — fixed Razorpay HTTPS URL
        return str((json.loads(resp.read().decode("utf-8")) or {}).get("status") or "")


def _cancel_payment_link(link_id: str) -> None:
    """Best effort: an unpaid link that no longer matches an upgrade must not stay payable."""
    from urllib.request import Request, urlopen

    auth = _razorpay_auth()
    if not auth or _is_stub_link(link_id):
        return
    req = Request(f"https://api.razorpay.com/v1/payment_links/{link_id}/cancel", data=b"{}", method="POST",
                  headers={"Content-Type": "application/json", "Authorization": auth})
    try:
        with urlopen(req, timeout=15):  # noqa: S310 — fixed Razorpay HTTPS URL
            pass
    except Exception:  # noqa: BLE001 - a paid-late link is still caught by handle_payment_link_event
        logger.warning("Could not cancel Razorpay payment link %s", link_id)


def guard_plan_change(sub, plan):
    """Called before a plan switch creates anything at Razorpay.

    While an upgrade is in progress the only allowed choices are: the same upgrade plan again
    (returns the existing links instead of charging twice) and, while its difference is unpaid, the
    old plan (undoes the upgrade). Anything else waits until the new plan starts. Returns
    ``(sub, remote_id)`` when the request is fully handled here, else ``None``.
    """
    if not upgrade_in_progress(sub):
        return None
    when = timezone.localtime(sub.current_period_end).strftime("%d %b %Y") if sub.current_period_end else "the period end"
    if plan.pk == sub.upgrade_plan_id:
        sub._proration_url = "" if sub.proration_paid_at else (sub.proration_link_url or "")
        sub._checkout_url = _pending_checkout_url(sub)
        return sub, (sub.pending_razorpay_subscription_id or sub.razorpay_subscription_id or "")
    if plan.pk == sub.plan_id and sub.proration_paid_at is None:
        cancel_upgrade(sub)
        sub._checkout_url = ""
        return sub, (sub.razorpay_subscription_id or "")
    if sub.proration_paid_at is not None:
        raise BusinessRuleError(
            f"Your upgrade to {sub.upgrade_plan.name} is paid and starts its own billing on {when}. "
            "You can change plans again after that.",
            code="PLAN_CHANGE_IN_PROGRESS",
        )
    raise BusinessRuleError(
        f"Your upgrade to {sub.upgrade_plan.name} is waiting for its payment. Pay the difference, or choose "
        f"{sub.plan.name} to undo it, before picking another plan.",
        code="PLAN_CHANGE_IN_PROGRESS",
    )


def _pending_checkout_url(sub) -> str:
    """The new plan's mandate approval page, read back from Razorpay (best effort)."""
    pending = (sub.pending_razorpay_subscription_id or "").strip()
    if not pending or sub.pending_authenticated_at:
        return ""
    from .services import fetch_razorpay_subscription

    try:
        return str((fetch_razorpay_subscription(pending) or {}).get("short_url") or "")
    except Exception:  # noqa: BLE001
        return ""


def start_upgrade(sub, plan, *, now=None) -> str:
    """Apply ``plan`` now and ask for the prorated difference. Returns the payment link URL.

    Only for an ACTIVE subscription inside a paid period with no upgrade already in progress
    (``guard_plan_change`` runs first), so the difference is always from the plan being paid for.
    """
    now = now or timezone.now()
    if sub.status != sub.Status.ACTIVE or not sub.current_period_end or sub.current_period_end <= now:
        raise BusinessRuleError("An upgrade needs a paid billing period in progress.", code="UPGRADE_NO_PERIOD")
    amount = proration_paise(
        old_price=int(sub.plan.price_paise or 0), new_price=int(plan.price_paise or 0),
        period_end=sub.current_period_end, now=now,
    )
    sub.upgrade_plan = plan
    sub.upgrade_started_at = now
    sub.proration_amount_paise = amount
    sub.proration_paid_at = None
    url = ""
    if amount > 0:
        sub.upgrade_grace_until = now + GRACE
        link_id, url = _create_payment_link(
            sub.company, amount_paise=amount,
            description=f"Upgrade to {plan.name} for the rest of this billing period",
            notes={"kind": "proration", "company_id": sub.company_id, "plan": plan.slug},
            expire_by=now + GRACE,
        )
        sub.proration_link_id = link_id
        sub.proration_link_url = url
    else:
        sub.proration_link_id = ""
        sub.proration_link_url = ""
        sub.proration_paid_at = now  # nothing to pay (the last moments of the period)
        sub.upgrade_grace_until = _paid_until(sub, now)
    sub.save(update_fields=[
        "upgrade_plan", "upgrade_started_at", "upgrade_grace_until", "proration_amount_paise",
        "proration_link_id", "proration_link_url", "proration_paid_at", "updated_at",
    ])
    return url


def clear_upgrade(sub, update_fields: list[str] | None = None) -> None:
    """The new plan's own subscription is active (or the upgrade ended): drop the overlay. An
    unpaid prorated link is cancelled so it can't be paid for an upgrade that no longer exists."""
    if sub.proration_paid_at is None and sub.proration_link_id:
        _cancel_payment_link(sub.proration_link_id)
    sub.upgrade_plan = None
    sub.upgrade_started_at = None
    sub.upgrade_grace_until = None
    sub.proration_link_id = ""
    sub.proration_link_url = ""
    fields = ["upgrade_plan", "upgrade_started_at", "upgrade_grace_until", "proration_link_id", "proration_link_url"]
    if update_fields is not None:
        update_fields.extend(f for f in fields if f not in update_fields)
    else:
        sub.save(update_fields=[*fields, "updated_at"])


def cancel_upgrade(sub) -> None:
    """The owner chose the old plan again before paying the difference: undo the upgrade now."""
    from .models import Subscription
    from .services import _cancel_razorpay_subscription

    with transaction.atomic():
        locked = Subscription.objects.select_for_update().get(pk=sub.pk)
        if locked.proration_paid_at is not None or not locked.upgrade_plan_id:
            return
        pending = (locked.pending_razorpay_subscription_id or "").strip()
        if pending and locked.pending_plan_id == locked.upgrade_plan_id:
            if not _cancel_razorpay_subscription(pending, at_cycle_end=False):
                raise BusinessRuleError("Could not cancel the new plan's subscription. Try again in a minute.")
            locked.pending_razorpay_subscription_id = ""
            locked.pending_plan = None
            locked.pending_authenticated_at = None
        fields: list[str] = []
        clear_upgrade(locked, fields)
        locked.save(update_fields=[
            *fields, "pending_razorpay_subscription_id", "pending_plan", "pending_authenticated_at", "updated_at",
        ])
    sub.refresh_from_db()


def handle_payment_link_event(payload: dict) -> dict:
    """``payment_link.paid``: mark the proration paid and issue its GST invoice (once).

    A paid link that matches no upgrade any more (superseded, or the upgrade already ended) is
    still invoiced — the money was taken — and parked on the dead-letter queue for staff to refund
    or credit, instead of being dropped.
    """
    from decimal import Decimal

    from accounts.models import Company
    from core.rls import rls_bypass

    from .models import Subscription
    from .platform_gst import issue_platform_gst_invoice
    from .services import park_dead_letter

    event = str(payload.get("event") or "")
    body = payload.get("payload") or {}
    link = ((body.get("payment_link") or {}).get("entity")) or {}
    payment = ((body.get("payment") or {}).get("entity")) or {}
    link_id = str(link.get("id") or "")
    if event != "payment_link.paid" or not link_id:
        return {"ok": True, "ignored": True}
    payment_id = str(payment.get("id") or "")
    try:
        paise = int(payment.get("amount") or link.get("amount_paid") or 0)
    except (TypeError, ValueError):
        paise = 0
    with rls_bypass():
        with transaction.atomic():
            sub = Subscription.objects.select_for_update().filter(proration_link_id=link_id).select_related("company").first()
            if sub is not None and sub.proration_paid_at is None:
                now = timezone.now()
                sub.proration_paid_at = now
                sub.upgrade_grace_until = _paid_until(sub, now)
                sub.save(update_fields=["proration_paid_at", "upgrade_grace_until", "updated_at"])
        if sub is not None:
            company = sub.company
        else:
            cid = str((link.get("notes") or {}).get("company_id") or "")
            company = Company.objects.filter(pk=int(cid)).first() if cid.isdigit() else None
            if company is None:
                logger.warning("Paid payment link %s matches no company", link_id)
                return {"ok": True, "ignored": True}
        if payment_id and paise > 0:
            issue_platform_gst_invoice(company, provider="razorpay", capture_id=payment_id,
                                       amount=Decimal(paise) / Decimal(100))
        if sub is None:
            park_dead_letter(
                provider="razorpay_payment_link", event_id=f"orphan:{link_id}",
                payload=payload if isinstance(payload, dict) else {},
                error="A prorated upgrade link was paid after the upgrade changed or ended: refund or credit it.",
                company=company,
            )
            return {"ok": True, "parked": True}
    return {"ok": True, "proration_paid": True}


def revert_unpaid_upgrades(now=None) -> int:
    """Daily: an upgrade whose prorated charge was not paid in time goes back to the old plan.

    The link is checked at Razorpay first (a lost webhook must not revert someone who paid). The
    new plan's pending subscription is cancelled unless its mandate was already approved — then
    the owner agreed to the new price from the next renewal and only the early access ends. A paid
    upgrade whose period is over (its new mandate was never approved) just loses the overlay.
    """
    from core.rls import rls_bypass

    from .models import Subscription
    from .services import _cancel_razorpay_subscription

    now = now or timezone.now()
    n = 0
    with rls_bypass():
        due = list(
            Subscription.objects.filter(upgrade_plan__isnull=False, upgrade_grace_until__lte=now)
            .values_list("pk", flat=True)
        )
        for pk in due:
            try:
                status = ""
                with transaction.atomic():
                    sub = Subscription.objects.select_for_update().select_related("company", "plan").get(pk=pk)
                    if sub.upgrade_plan_id is None or not sub.upgrade_grace_until or sub.upgrade_grace_until > now:
                        continue
                    if sub.proration_paid_at is None and sub.proration_link_id:
                        status = _payment_link_status(sub.proration_link_id)
                        if status == "paid":
                            sub.proration_paid_at = now
                            sub.upgrade_grace_until = _paid_until(sub, now)
                            sub.save(update_fields=["proration_paid_at", "upgrade_grace_until", "updated_at"])
                            continue
                    unpaid = sub.proration_paid_at is None
                    pending = (sub.pending_razorpay_subscription_id or "").strip()
                    if unpaid and pending and sub.pending_plan_id == sub.upgrade_plan_id and not sub.pending_authenticated_at:
                        if not _cancel_razorpay_subscription(pending, at_cycle_end=False):
                            logger.warning("Upgrade revert for sub %s waits: cancel of %s failed", pk, pending)
                            continue
                        sub.pending_razorpay_subscription_id = ""
                        sub.pending_plan = None
                    fields: list[str] = []
                    clear_upgrade(sub, fields)
                    sub.save(update_fields=[*fields, "pending_razorpay_subscription_id", "pending_plan", "updated_at"])
            except Exception:  # noqa: BLE001 - one subscription's gateway error must not stop the rest
                logger.exception("Upgrade revert for subscription %s failed; retried tomorrow", pk)
                continue
            if unpaid:
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
