"""SaaS subscription helpers (BB-000671). Separate from document tax math in core.services.billing."""

from __future__ import annotations

from datetime import timedelta

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


def start_or_update_subscription(*, company, plan: Plan) -> tuple[Subscription, str]:
    """Create/update subscription. Returns (subscription, checkout_order_id)."""
    now = timezone.now()
    stub_order = f"stub_order_{company.pk}_{plan.pk}_{int(now.timestamp())}"
    razorpay_key = (getattr(settings, "RAZORPAY_KEY_ID", "") or "").strip()
    razorpay_secret = (getattr(settings, "RAZORPAY_KEY_SECRET", "") or "").strip()

    # BB-000725: stay PENDING until Razorpay webhook (never ACTIVE on stub checkout).
    defaults = {
        "plan": plan,
        "status": Subscription.Status.PENDING,
        "current_period_end": None,
        "trial_ends_at": None,
    }
    sub, _created = Subscription.objects.update_or_create(company=company, defaults=defaults)

    checkout_order_id = stub_order
    if razorpay_key and razorpay_secret and plan.razorpay_plan_id:
        remote_id = _create_razorpay_subscription(plan, company)
        if remote_id:
            sub.razorpay_subscription_id = remote_id
            sub.status = Subscription.Status.TRIAL
            sub.trial_ends_at = now + timedelta(days=14)
            sub.save(update_fields=["razorpay_subscription_id", "status", "trial_ends_at", "updated_at"])
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
    except Exception:  # noqa: BLE001 — fall back to stub checkout
        return ""
    return str(payload.get("id") or "")


def apply_razorpay_subscription_status(*, razorpay_subscription_id: str, rzp_status: str) -> Subscription | None:
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
        sub.current_period_end = timezone.now() + timedelta(days=30)
        update_fields.append("current_period_end")
    sub.save(update_fields=update_fields)
    return sub


def _map_razorpay_status(rzp_status: str) -> str | None:
    status = (rzp_status or "").strip().lower()
    if status == "active":
        return Subscription.Status.ACTIVE
    if status in {"halted", "paused", "pending"}:
        return Subscription.Status.PAST_DUE
    if status in {"cancelled", "completed", "expired"}:
        return Subscription.Status.SUSPENDED
    return None
