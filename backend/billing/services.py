"""SaaS subscription helpers (BB-000671). Separate from document tax math in core.services.billing."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.utils import timezone

from .models import Plan, Subscription


def subscription_for_company(company):
    if company is None:
        return None
    return (
        Subscription.objects.select_related("plan", "company")
        .filter(company_id=company.pk)
        .first()
    )


def company_writes_blocked(company) -> bool:
    if company is None:
        return False
    if getattr(company, "billing_override_active", False):
        return False
    sub = subscription_for_company(company)
    # BB-000725: paid envs require a subscription unless override is active.
    if sub is None:
        return bool(getattr(settings, "REQUIRE_SUBSCRIPTION", False))
    return sub.is_write_blocked()


def plan_modules_for_company(company) -> dict | None:
    sub = subscription_for_company(company)
    if sub is None or sub.plan_id is None:
        return None
    modules = getattr(sub.plan, "modules", None)
    return modules if isinstance(modules, dict) else None


def ensure_register_trial(company) -> Subscription | None:
    """Give a new tenant a time-boxed TRIAL so REQUIRE_SUBSCRIPTION does not write-block them."""
    if Subscription.objects.filter(company=company).exists():
        return None
    days = int(getattr(settings, "BILLING_TRIAL_DAYS", 14) or 14)
    plan, _ = Plan.objects.get_or_create(
        slug="trial",
        defaults={
            "name": "Trial",
            "seat_limit": 3,
            "price_paise": 0,
            "is_active": True,
            "modules": {},
        },
    )
    return Subscription.objects.create(
        company=company,
        plan=plan,
        status=Subscription.Status.TRIAL,
        trial_ends_at=timezone.now() + timedelta(days=days),
    )


def start_or_update_subscription(*, company, plan: Plan) -> tuple[Subscription, str]:
    """Create/update subscription. Returns (subscription, checkout_order_id)."""
    now = timezone.now()
    razorpay_key = (getattr(settings, "RAZORPAY_KEY_ID", "") or "").strip()
    razorpay_secret = (getattr(settings, "RAZORPAY_KEY_SECRET", "") or "").strip()
    env = (getattr(settings, "DJANGO_ENV", "") or "").lower()
    if env in ("production", "staging") and not (razorpay_key and razorpay_secret and plan.razorpay_plan_id):
        from core.exceptions import BusinessRuleError

        raise BusinessRuleError("Razorpay is not configured; cannot start checkout.")
    stub_order = f"stub_order_{company.pk}_{plan.pk}_{int(now.timestamp())}"

    # Do not overwrite ACTIVE/TRIAL to PENDING — that write-blocks a paying tenant.
    live = {Subscription.Status.ACTIVE, Subscription.Status.TRIAL}
    live_razorpay = bool(razorpay_key and razorpay_secret and plan.razorpay_plan_id)
    sub = Subscription.objects.filter(company=company).first()
    created_new = False
    snapshot = None
    if sub is None:
        # B9-017: a brand-new subscription starts on a short TRIAL, not PENDING —
        # a webhook that never lands then just lets the trial expire on schedule
        # instead of permanently write-blocking a tenant who paid.
        days = int(
            getattr(settings, "BILLING_CHECKOUT_TRIAL_DAYS", 3) or 3
        ) if live_razorpay else int(getattr(settings, "BILLING_TRIAL_DAYS", 14) or 14)
        sub = Subscription.objects.create(
            company=company,
            plan=plan,
            status=Subscription.Status.TRIAL,
            current_period_end=None,
            trial_ends_at=now + timedelta(days=days),
        )
        created_new = True
    else:
        snapshot = (sub.status, sub.current_period_end, sub.trial_ends_at, sub.plan_id)
        if live_razorpay and sub.status in live:
            # Keep the live plan until Razorpay confirms the new subscription.
            pass
        else:
            sub.plan = plan
            if live_razorpay and sub.status not in live:
                sub.status = Subscription.Status.PENDING
                sub.current_period_end = None
                sub.trial_ends_at = None
            sub.save(update_fields=["plan", "status", "current_period_end", "trial_ends_at", "updated_at"])

    checkout_order_id = stub_order
    if razorpay_key and razorpay_secret and plan.razorpay_plan_id:
        prior_remote_id = (sub.razorpay_subscription_id or "").strip()
        try:
            remote_id = _create_razorpay_subscription(plan, company)
        except Exception:
            if created_new:
                sub.delete()
            elif snapshot is not None:
                sub.status, sub.current_period_end, sub.trial_ends_at, sub.plan_id = snapshot
                sub.save(update_fields=["plan", "status", "current_period_end", "trial_ends_at", "updated_at"])
            raise
        if remote_id:
            # B9-001: retire the old Razorpay subscription so the customer is
            # not billed on two subscriptions after a plan switch.
            if prior_remote_id and prior_remote_id != remote_id:
                _cancel_razorpay_subscription(prior_remote_id, at_cycle_end=True)
            sub.plan = plan
            sub.razorpay_subscription_id = remote_id
            if sub.status not in live:
                sub.status = Subscription.Status.PENDING
            sub.save(update_fields=["plan", "razorpay_subscription_id", "status", "updated_at"])
            checkout_order_id = remote_id
    return sub, checkout_order_id


def _create_razorpay_subscription(plan: Plan, company) -> str:
    import json
    from urllib.request import Request, urlopen

    key = (getattr(settings, "RAZORPAY_KEY_ID", "") or "").strip()
    secret = (getattr(settings, "RAZORPAY_KEY_SECRET", "") or "").strip()
    if not key or not secret or not plan.razorpay_plan_id:
        return ""
    body = json.dumps(
        {
            "plan_id": plan.razorpay_plan_id,
            "total_count": 120,
            "customer_notify": 1,
            "notes": {"company_id": str(company.pk)},
        }
    ).encode("utf-8")
    req = Request(
        "https://api.razorpay.com/v1/subscriptions",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    import base64

    token = base64.b64encode(f"{key}:{secret}".encode()).decode()
    req.add_header("Authorization", f"Basic {token}")
    try:
        with urlopen(req, timeout=15) as resp:  # noqa: S310 — fixed Razorpay HTTPS URL
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        from core.exceptions import BusinessRuleError

        raise BusinessRuleError("Could not create Razorpay subscription. Try again or contact support.") from exc
    return str(payload.get("id") or "")


def _cancel_razorpay_subscription(subscription_id: str, *, at_cycle_end: bool = True) -> None:
    """B9-001: cancel the tenant's previous Razorpay subscription so a plan
    switch does not leave two subscriptions billing the same customer. Best
    effort — a failure here must not block the new subscription."""
    import base64
    import json
    from urllib.request import Request, urlopen

    sid = (subscription_id or "").strip()
    key = (getattr(settings, "RAZORPAY_KEY_ID", "") or "").strip()
    secret = (getattr(settings, "RAZORPAY_KEY_SECRET", "") or "").strip()
    if not sid or not key or not secret:
        return
    body = json.dumps({"cancel_at_cycle_end": 1 if at_cycle_end else 0}).encode("utf-8")
    req = Request(
        f"https://api.razorpay.com/v1/subscriptions/{sid}/cancel",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Basic " + base64.b64encode(f"{key}:{secret}".encode()).decode(),
        },
    )
    try:
        with urlopen(req, timeout=15):  # noqa: S310 — fixed Razorpay HTTPS URL
            pass
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).warning(
            "Could not cancel prior Razorpay subscription %s", sid
        )


def apply_razorpay_subscription_status(
    razorpay_subscription_id: str,
    rzp_status: str,
    current_end: Any = None,
) -> Subscription | None:
    if not razorpay_subscription_id:
        return None
    sub = Subscription.objects.filter(razorpay_subscription_id=razorpay_subscription_id).first()
    if sub is None:
        return None
    mapped = _map_razorpay_status(rzp_status)
    if mapped is None:
        return sub
    update_fields = ["status", "updated_at"]
    sub.status = mapped
    if mapped == Subscription.Status.ACTIVE:
        if isinstance(current_end, (int, float)) and current_end > 0:
            from datetime import datetime, timezone as dt_timezone
            sub.current_period_end = datetime.fromtimestamp(current_end, tz=dt_timezone.utc)
        elif hasattr(current_end, "year"):
            sub.current_period_end = current_end
        else:
            sub.current_period_end = timezone.now() + timedelta(days=30)
        update_fields.append("current_period_end")
    sub.save(update_fields=update_fields)
    return sub


def _map_razorpay_status(rzp_status: str) -> str | None:
    status = (rzp_status or "").strip().lower()
    if status == "active":
        return Subscription.Status.ACTIVE
    if status == "authenticated":
        return None
    if status in {"halted", "paused"}:
        return Subscription.Status.PAST_DUE
    if status == "pending":
        # SUB-04: Razorpay leaves a subscription `pending` when an auto-charge
        # retry is failing. That is a payment problem — move it to PAST_DUE
        # (write-grace still applies) rather than silently keeping the prior status.
        return Subscription.Status.PAST_DUE
    if status in {"cancelled", "completed", "expired"}:
        return Subscription.Status.SUSPENDED
    return None
