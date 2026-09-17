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
    # R-015: subscribed plan with a non-dict payload → {} (fail-closed).
    # Do not coerce a missing subscription (None) into {}.
    return modules if isinstance(modules, dict) else {}


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
        # B9-005: an already-live paying subscriber switching plans gets no
        # proration — the change takes effect at the next billing cycle, not
        # immediately. Schedule the new Razorpay subscription to start when
        # the current one's paid-for period ends, instead of starting (and
        # charging) it right away while the old one is still also billing
        # through cancel_at_cycle_end.
        is_live_switch = (
            live_razorpay and sub.status in live and sub.plan_id != plan.pk and bool(prior_remote_id)
        )
        start_at = None
        if is_live_switch and sub.current_period_end and sub.current_period_end > now:
            start_at = int(sub.current_period_end.timestamp())
        try:
            remote_id = _create_razorpay_subscription(plan, company, start_at=start_at)
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
            sub.razorpay_subscription_id = remote_id
            if start_at is not None:
                # Deferred switch: keep the entitlements/plan the tenant already
                # paid for until the webhook confirms the new cycle started.
                sub.pending_plan = plan
                sub.save(update_fields=["pending_plan", "razorpay_subscription_id", "updated_at"])
            else:
                sub.plan = plan
                sub.pending_plan = None
                if sub.status not in live:
                    sub.status = Subscription.Status.PENDING
                sub.save(
                    update_fields=["plan", "pending_plan", "razorpay_subscription_id", "status", "updated_at"]
                )
            checkout_order_id = remote_id
    return sub, checkout_order_id


def _create_razorpay_subscription(plan: Plan, company, *, start_at: int | None = None) -> str:
    import json
    from urllib.request import Request, urlopen

    key = (getattr(settings, "RAZORPAY_KEY_ID", "") or "").strip()
    secret = (getattr(settings, "RAZORPAY_KEY_SECRET", "") or "").strip()
    if not key or not secret or not plan.razorpay_plan_id:
        return ""
    payload_body: dict[str, Any] = {
        "plan_id": plan.razorpay_plan_id,
        "total_count": 120,
        "customer_notify": 1,
        "notes": {"company_id": str(company.pk)},
    }
    if start_at is not None:
        # B9-005: defer the first charge to the given Unix timestamp (the
        # existing subscription's current_period_end) so a plan switch on a
        # live subscriber doesn't double-bill.
        payload_body["start_at"] = start_at
    body = json.dumps(payload_body).encode("utf-8")
    req = Request(
        "https://api.razorpay.com/v1/subscriptions",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    import base64

    token = base64.b64encode(f"{key}:{secret}".encode()).decode()
    req.add_header("Authorization", f"Basic {token}")
    from core.circuit_breaker import CircuitOpenError, call as circuit_call
    from core.exceptions import BusinessRuleError

    def _post():
        with urlopen(req, timeout=15) as resp:  # noqa: S310 — fixed Razorpay HTTPS URL
            return json.loads(resp.read().decode("utf-8"))

    try:
        payload = circuit_call("razorpay_subscriptions", _post, failure_threshold=5, cooldown_seconds=30)
    except CircuitOpenError as exc:
        raise BusinessRuleError(
            "Payments provider is temporarily unavailable. Try again shortly."
        ) from exc
    except Exception as exc:  # noqa: BLE001
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


def fetch_razorpay_subscription(subscription_id: str) -> dict | None:
    """GET /v1/subscriptions/{id}. None when keys or id are missing.

    Network/circuit failures raise so recon can park a DeadLetterEvent.
    """
    import base64
    import json
    from urllib.request import Request, urlopen

    sid = (subscription_id or "").strip()
    key = (getattr(settings, "RAZORPAY_KEY_ID", "") or "").strip()
    secret = (getattr(settings, "RAZORPAY_KEY_SECRET", "") or "").strip()
    if not sid or not key or not secret:
        return None
    req = Request(
        f"https://api.razorpay.com/v1/subscriptions/{sid}",
        method="GET",
        headers={
            "Authorization": "Basic " + base64.b64encode(f"{key}:{secret}".encode()).decode(),
        },
    )
    from core.circuit_breaker import call as circuit_call

    def _get():
        with urlopen(req, timeout=15) as resp:  # noqa: S310 — fixed Razorpay HTTPS URL
            return json.loads(resp.read().decode("utf-8"))

    payload = circuit_call("razorpay_subscriptions", _get, failure_threshold=5, cooldown_seconds=30)
    return payload if isinstance(payload, dict) else None


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
        # B9-005: the deferred plan switch's new subscription has now actually
        # started billing (Razorpay confirmed ACTIVE) -- promote the pending
        # plan the tenant only just started paying for.
        if sub.pending_plan_id:
            sub.plan = sub.pending_plan
            sub.pending_plan = None
            update_fields.extend(["plan", "pending_plan"])
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


def map_razorpay_status(rzp_status: str) -> str | None:
    """Public alias for recon / webhooks (8.6)."""
    return _map_razorpay_status(rzp_status)


def park_dead_letter(*, provider: str, event_id: str, payload: dict, error: str, company=None):
    from django.db import IntegrityError, transaction

    from .models import DeadLetterEvent

    trimmed_event_id = (event_id or "")[:128]
    try:
        # A savepoint: on IntegrityError only this INSERT rolls back, not
        # whatever outer transaction/atomic block the caller (a request view,
        # a recon loop) is already running inside -- without it, catching the
        # exception here still leaves the caller's transaction unusable for
        # the fallback SELECT below (Postgres/SQLite both poison the whole
        # transaction after an unhandled constraint violation).
        with transaction.atomic():
            event = DeadLetterEvent.objects.create(
                company=company,
                provider=provider,
                event_id=trimmed_event_id,
                payload=payload if isinstance(payload, dict) else {},
                error=(error or "")[:4000],
                status=DeadLetterEvent.Status.PENDING,
                attempts=1,
            )
    except IntegrityError:
        # billing_dlq_uniq_pending_provider_event closed a check-then-create
        # race here: a concurrent caller (e.g. overlapping recon runs, or a
        # webhook retry racing a manual replay trigger) already parked a
        # PENDING row for this provider/event_id. Return that row instead of
        # raising or creating a duplicate.
        existing = DeadLetterEvent.objects.filter(
            provider=provider, event_id=trimmed_event_id, status=DeadLetterEvent.Status.PENDING
        ).first()
        if existing is not None:
            return existing
        raise
    if company is not None:
        try:
            from insights.telemetry import record_journey_failed

            record_journey_failed(company, "payment", "5xx")
        except Exception:  # noqa: BLE001
            pass
    return event


def replay_dead_letter(event, *, user=None):
    """Re-apply a parked Razorpay subscription or payment-gateway webhook. Audited."""
    from decimal import Decimal

    from django.utils import timezone as dj_tz

    from core.services.audit import AuditService

    from .models import DeadLetterEvent

    if event.status == DeadLetterEvent.Status.REPLAYED:
        return event
    payload = event.payload if isinstance(event.payload, dict) else {}
    event.attempts = int(event.attempts or 0) + 1
    meta = {}
    company = event.company
    if payload.get("kind") == "payment_webhook":
        from payments.models import PaymentLink
        from payments.services import PaymentService

        link = None
        plid = payload.get("payment_link_id")
        if plid:
            qs = PaymentLink.objects.filter(pk=plid)
            if event.company_id:
                qs = qs.filter(company_id=event.company_id)
            link = qs.first()
        if link is None and payload.get("provider_link_id"):
            qs = PaymentLink.objects.filter(provider_link_id=payload["provider_link_id"])
            if event.company_id:
                qs = qs.filter(company_id=event.company_id)
            link = qs.first()
        company = event.company or (link.company if link is not None else None)
        PaymentService.finalize_gateway_payment(
            company=company,
            provider=str(payload.get("provider") or event.provider or ""),
            provider_payment_id=str(payload.get("provider_payment_id") or event.event_id or ""),
            amount=Decimal(str(payload.get("amount") or "0")),
            fee=Decimal(str(payload.get("fee") or "0")),
            payment_link=link,
            raw_payload=payload.get("raw") or {},
        )
        meta = {"kind": "payment_webhook"}
    else:
        nested = (((payload.get("payload") or {}).get("subscription") or {}).get("entity")) or {}
        if not nested and payload.get("entity") == "subscription":
            nested = payload
        rzp_id = str(nested.get("id") or event.event_id or "")
        rzp_status = str(nested.get("status") or "")
        sub = apply_razorpay_subscription_status(
            razorpay_subscription_id=rzp_id,
            rzp_status=rzp_status,
            current_end=nested.get("current_end"),
        )
        company = event.company or (sub.company if sub else None)
        meta = {"razorpay_status": rzp_status}
    event.status = DeadLetterEvent.Status.REPLAYED
    event.replayed_at = dj_tz.now()
    event.replayed_by = user
    event.save(update_fields=["status", "replayed_at", "replayed_by", "attempts", "updated_at"])
    AuditService.log(
        action="billing.dlq_replay",
        company=company,
        user=user,
        entity_type="DeadLetterEvent",
        entity_id=event.pk,
        description=f"Replayed {event.provider} {event.event_id}.",
        metadata=meta,
    )
    return event

