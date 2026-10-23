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
    from .plan_change import effective_plan

    modules = getattr(effective_plan(sub), "modules", None)  # WP-BL3: an upgrade applies at once
    # R-015: subscribed plan with a non-dict payload → {} (fail-closed).
    # Do not coerce a missing subscription (None) into {}.
    return modules if isinstance(modules, dict) else {}


# Held flags must be stored as False. A missing grantable key is not a denial:
# ``_entitled`` and ``build_feature_flags`` both allow a key the plan omits,
# so a pack or a company JSON True can turn the surface on.
# H0 and H1 ship together. GSTR worksheets are granted. GSTN upload stays off.
TRIAL_HELD_FALSE = frozenset({
    "ENABLE_LEGACY_IMPORT",
    "ENABLE_COMPLAINTS",
    "ENABLE_SUPPORT_TICKETS",
    "ENABLE_CONTRACTS",
    "ENABLE_REFERRALS",
    "ENABLE_CROSS_SELL",
    "ENABLE_TALLY",
    "ENABLE_GSTN_JSON",
    "ENABLE_WORKSHOP",
    "ENABLE_PROJECTS",
    "ENABLE_INSURANCE",
    "ENABLE_ROUTE_OPTIMIZATION",
    "ENABLE_ROUTE_PROFIT",
    "ENABLE_PURCHASE_PLANNING",
    "ENABLE_PREDICTIVE_DUNNING",
    "ENABLE_ARCHETYPE_PACKS",
    "ENABLE_CUSTOMER_ACTIONS",
})


def trial_plan_modules() -> dict:
    """Every grantable flag, explicit True or False.

    Dark modules (CRM, manufacturing, payroll) stay unnamed. ``ENABLE_GSTR``
    is True because the return pages are worksheets, not a GSTN filing.
    ``ENABLE_CUSTOMER_360`` stays True so a later complaints grant can render
    on the customer page.
    """
    from core.services.feature_flags import ROLLOUT_GRANTABLE_KEYS

    modules = {key: True for key in sorted(ROLLOUT_GRANTABLE_KEYS)}
    # Not grantable: company JSON cannot lift it. Stored false so a trial
    # subscription still denies the GSTN-shaped export when the env is on.
    modules["ENABLE_GSTN_JSON"] = False
    for key in TRIAL_HELD_FALSE:
        if key in modules:
            modules[key] = False
    return modules


def grandfather_trial_module_use() -> dict[str, int]:
    """Keep a module for trial companies that already stored rows in it.

    Runs in the same transaction as the trial-plan update. Does not delete
    rows, does not clear an explicit False, and does not change a company
    that already has the flag set. Only a job card, a project, or an
    insurance policy, option set, or product qualifies.
    """
    from accounts.models import Company
    from billing.models import Subscription

    kept = {"ENABLE_WORKSHOP": 0, "ENABLE_PROJECTS": 0, "ENABLE_INSURANCE": 0}
    company_ids = set(
        Subscription.objects.filter(plan__slug="trial").values_list("company_id", flat=True)
    )
    if not company_ids:
        return kept

    from insurance.models import Policy, PolicyOptionSet, PolicyProduct
    from projects.models import Project
    from workshop.models import JobCard

    used = {
        "ENABLE_WORKSHOP": set(
            JobCard.objects.filter(company_id__in=company_ids).values_list("company_id", flat=True)
        ),
        "ENABLE_PROJECTS": set(
            Project.objects.filter(company_id__in=company_ids).values_list("company_id", flat=True)
        ),
        "ENABLE_INSURANCE": set(
            Policy.objects.filter(company_id__in=company_ids).values_list("company_id", flat=True)
        )
        | set(
            PolicyOptionSet.objects.filter(company_id__in=company_ids).values_list(
                "company_id", flat=True
            )
        )
        | set(
            PolicyProduct.objects.filter(company_id__in=company_ids).values_list(
                "company_id", flat=True
            )
        ),
    }
    for company in Company.objects.filter(id__in=company_ids):
        flags = dict(company.feature_flags or {})
        changed = False
        for key, ids in used.items():
            if company.id not in ids or key in flags:
                continue
            flags[key] = True
            kept[key] += 1
            changed = True
        if changed:
            company.feature_flags = flags
            company.save(update_fields=["feature_flags"])
    return kept


def ensure_register_trial(company, owner=None) -> Subscription | None:
    """Give a new tenant a time-boxed TRIAL so REQUIRE_SUBSCRIPTION does not write-block them.

    WP-AB3: a business that already had a trial (same GSTIN/PAN, or same phone and email) gets the
    trial row already ended — the account works read-only and the billing page offers plans.
    """
    if Subscription.objects.filter(company=company).exists():
        return None
    from .trial_guard import record_trial, trial_used_before

    days = int(getattr(settings, "BILLING_TRIAL_DAYS", 14) or 14)
    repeat = trial_used_before(company, owner)
    plan, _ = Plan.objects.get_or_create(
        slug="trial",
        defaults={
            "name": "Trial",
            "seat_limit": 3,
            "price_paise": 0,
            "is_active": True,
            "modules": trial_plan_modules(),
        },
    )
    sub = Subscription.objects.create(
        company=company,
        plan=plan,
        status=Subscription.Status.TRIAL,
        trial_ends_at=timezone.now() if repeat else timezone.now() + timedelta(days=days),
        churn_reason="TRIAL_ALREADY_USED" if repeat else "",
    )
    if not repeat:
        record_trial(company, owner)
    return sub


def end_trial_if_repeat(company, owner=None) -> bool:
    """WP-AB3: a GSTIN entered after sign-up (setup wizard) that matches an earlier trial ends the
    running trial now. Returns True when it did."""
    from .trial_guard import record_trial, trial_used_before

    sub = Subscription.objects.filter(company=company, status=Subscription.Status.TRIAL).first()
    if sub is None or not sub.trial_ends_at or sub.trial_ends_at <= timezone.now():
        # No trial running (it is over, or the company already pays): still remember the GSTIN, so
        # the same business can't start a fresh trial under a new phone and email.
        record_trial(company, owner)
        return False
    if not trial_used_before(company, owner):
        record_trial(company, owner)
        return False
    sub.trial_ends_at = timezone.now()
    sub.churn_reason = "TRIAL_ALREADY_USED"
    sub.save(update_fields=["trial_ends_at", "churn_reason", "updated_at"])
    return True


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
        if live_razorpay:
            # Keep status, period end, and the paid plan until Razorpay
            # confirms. Flipping an older subscription to PENDING and clearing
            # current_period_end write-blocks the tenant before they can pay.
            pass
        else:
            sub.plan = plan
            sub.save(update_fields=["plan", "updated_at"])

    checkout_order_id = stub_order
    if razorpay_key and razorpay_secret and plan.razorpay_plan_id:
        prior_remote_id = (sub.razorpay_subscription_id or "").strip()
        # Clicking the plan the tenant already pays for must not open a
        # second subscription. That used to bill both until cycle end.
        from .plan_change import guard_plan_change

        handled = guard_plan_change(sub, plan)  # WP-BL3: one upgrade at a time, never charged twice
        if handled is not None:
            return handled
        if (
            sub.status in live
            and prior_remote_id
            and sub.plan_id == plan.pk
            and not (sub.pending_razorpay_subscription_id or "").strip()
        ):
            sub._checkout_url = ""
            return sub, prior_remote_id
        # B9-005: an already-live paying subscriber switching plans gets no
        # proration — the change takes effect at the next billing cycle, not
        # immediately. Schedule the new Razorpay subscription to start when
        # the current one's paid-for period ends. Do not cancel the paid
        # subscription until that new one is confirmed active.
        is_live_switch = (
            live_razorpay and sub.status in live and sub.plan_id != plan.pk and bool(prior_remote_id)
        )
        start_at = None
        if is_live_switch and sub.current_period_end and sub.current_period_end > now:
            start_at = int(sub.current_period_end.timestamp())
        # WP-BL3: an upgrade (charged now, prorated) needs a paid period in progress; a TRIAL or a
        # lapsed period just switches. Any other change to a plan with lower limits is checked
        # against current use first, whatever the status.
        is_upgrade = (
            is_live_switch
            and sub.status == Subscription.Status.ACTIVE
            and bool(sub.current_period_end and sub.current_period_end > now)
            and int(plan.price_paise or 0) > int(sub.plan.price_paise or 0)
        )
        if sub.plan_id != plan.pk and not is_upgrade:
            from .plan_change import check_downgrade

            check_downgrade(company, plan)  # WP-BL3: refuse a downgrade below current use
        try:
            created = _create_razorpay_subscription(plan, company, start_at=start_at)
        except Exception:
            if created_new:
                sub.delete()
            elif snapshot is not None:
                sub.status, sub.current_period_end, sub.trial_ends_at, sub.plan_id = snapshot
                sub.save(update_fields=["plan", "status", "current_period_end", "trial_ends_at", "updated_at"])
            raise
        if isinstance(created, tuple):
            remote_id = str(created[0] or "")
            short_url = str(created[1] or "") if len(created) > 1 else ""
        else:
            remote_id = str(created or "")
            short_url = ""
        if remote_id:
            if prior_remote_id and prior_remote_id != remote_id:
                old_pending = (sub.pending_razorpay_subscription_id or "").strip()
                if old_pending and old_pending != remote_id:
                    # A second plan switch before the first one's webhook
                    # landed would otherwise orphan `old_pending` -- it stops
                    # matching either id on `sub` once overwritten below, so
                    # a late webhook/checkout for it becomes a silent no-op
                    # (see apply_razorpay_subscription_status). Best effort,
                    # same as the live-subscription cancel path above.
                    _cancel_razorpay_subscription(old_pending, at_cycle_end=False)
                sub.pending_razorpay_subscription_id = remote_id
                sub.pending_plan = plan
                sub.pending_authenticated_at = None
                sub.save(update_fields=[
                    "pending_plan", "pending_razorpay_subscription_id", "pending_authenticated_at", "updated_at",
                ])
                if is_upgrade:
                    from .plan_change import start_upgrade

                    sub._proration_url = start_upgrade(sub, plan, now=now)
            elif sub.plan_id != plan.pk:
                sub.razorpay_subscription_id = remote_id
                sub.pending_plan = plan
                sub.save(update_fields=["pending_plan", "razorpay_subscription_id", "updated_at"])
            else:
                sub.razorpay_subscription_id = remote_id
                sub.pending_plan = None
                sub.save(update_fields=["pending_plan", "razorpay_subscription_id", "updated_at"])
            checkout_order_id = remote_id
            sub._checkout_url = short_url
    return sub, checkout_order_id


def _create_razorpay_subscription(plan: Plan, company, *, start_at: int | None = None) -> tuple[str, str]:
    import json
    from urllib.request import Request, urlopen

    key = (getattr(settings, "RAZORPAY_KEY_ID", "") or "").strip()
    secret = (getattr(settings, "RAZORPAY_KEY_SECRET", "") or "").strip()
    if not key or not secret or not plan.razorpay_plan_id:
        return "", ""
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
    return str(payload.get("id") or ""), str(payload.get("short_url") or "")


def _cancel_razorpay_subscription(subscription_id: str, *, at_cycle_end: bool = True) -> bool:
    """B9-001: cancel the tenant's previous Razorpay subscription so a plan
    switch does not leave two subscriptions billing the same customer. Best
    effort — a failure here must not block the new subscription. Returns False
    when the call failed, so a caller that must not forget a live subscription
    (the upgrade revert) can keep its id and retry."""
    import base64
    import json
    from urllib.request import Request, urlopen

    sid = (subscription_id or "").strip()
    key = (getattr(settings, "RAZORPAY_KEY_ID", "") or "").strip()
    secret = (getattr(settings, "RAZORPAY_KEY_SECRET", "") or "").strip()
    if not sid or not key or not secret:
        return True
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
        return False
    return True


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


def fetch_razorpay_paid_charges(subscription_id: str) -> list[dict]:
    """WP-BL2: paid charges of one Razorpay subscription (GET /v1/invoices?subscription_id=).

    ``[{"payment_id", "amount", "paid_at"}]`` with ``amount`` in rupees, GST inclusive, and
    ``paid_at`` a Unix time (0 when Razorpay did not say). Empty when keys or id
    are missing. Network/circuit failures raise so recon can park a DeadLetterEvent.
    """
    import base64
    import json
    from decimal import Decimal
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen

    sid = (subscription_id or "").strip()
    key = (getattr(settings, "RAZORPAY_KEY_ID", "") or "").strip()
    secret = (getattr(settings, "RAZORPAY_KEY_SECRET", "") or "").strip()
    if not sid or not key or not secret:
        return []
    req = Request(
        "https://api.razorpay.com/v1/invoices?" + urlencode({"subscription_id": sid, "count": 100}),
        method="GET",
        headers={"Authorization": "Basic " + base64.b64encode(f"{key}:{secret}".encode()).decode()},
    )
    from core.circuit_breaker import call as circuit_call

    def _get():
        with urlopen(req, timeout=15) as resp:  # noqa: S310 - fixed Razorpay HTTPS URL
            return json.loads(resp.read().decode("utf-8"))

    payload = circuit_call("razorpay_subscriptions", _get, failure_threshold=5, cooldown_seconds=30)
    out = []
    for item in (payload or {}).get("items") or []:
        if str(item.get("status") or "") != "paid" or not item.get("payment_id"):
            continue
        try:
            paise = int(item.get("amount_paid") or 0)  # what was collected, never the gross
            paid_at = int(item.get("paid_at") or 0)
        except (TypeError, ValueError):
            continue
        if paise > 0:
            out.append({
                "payment_id": str(item["payment_id"]), "amount": Decimal(paise) / Decimal(100), "paid_at": paid_at,
            })
    return out


def razorpay_refund(
    payment_id: str, amount_paise: int, *, notes: dict | None = None, idempotency_key: str = "",
) -> str:
    """WP-BL1: POST /v1/payments/{id}/refund for part of a captured payment. Returns the refund id.

    Raises when keys are missing or the gateway refuses, so the caller can stop and retry later.
    ``idempotency_key`` (PAY-09) makes a retry of the same refund return the first one instead of
    refunding again.
    """
    import base64
    import json
    from urllib.request import Request, urlopen

    from core.exceptions import BusinessRuleError

    key = (getattr(settings, "RAZORPAY_KEY_ID", "") or "").strip()
    secret = (getattr(settings, "RAZORPAY_KEY_SECRET", "") or "").strip()
    if not key or not secret:
        raise BusinessRuleError("Razorpay keys are not configured; refund by hand.")
    if not payment_id or amount_paise <= 0:
        raise BusinessRuleError("Nothing to refund.")
    body: dict[str, Any] = {"amount": int(amount_paise), "notes": {k: str(v) for k, v in (notes or {}).items()}}
    headers = {
        "Authorization": "Basic " + base64.b64encode(f"{key}:{secret}".encode()).decode(),
        "Content-Type": "application/json",
    }
    if idempotency_key:
        headers["X-Razorpay-Idempotency-Key"] = idempotency_key[:64]
        body["receipt"] = idempotency_key[:40]
    req = Request(
        f"https://api.razorpay.com/v1/payments/{payment_id}/refund",
        data=json.dumps(body).encode(),
        method="POST",
        headers=headers,
    )
    from core.circuit_breaker import call as circuit_call

    def _post():
        with urlopen(req, timeout=20) as resp:  # noqa: S310 - fixed Razorpay HTTPS URL
            return json.loads(resp.read().decode("utf-8"))

    payload = circuit_call("razorpay_refunds", _post, failure_threshold=3, cooldown_seconds=60)
    refund_id = str((payload or {}).get("id") or "")
    if not refund_id:
        raise BusinessRuleError("Razorpay did not return a refund id.")
    return refund_id


def _subscription_for_razorpay_id(razorpay_subscription_id: str):
    sub = Subscription.objects.filter(razorpay_subscription_id=razorpay_subscription_id).first()
    if sub is not None:
        return sub, False
    sub = Subscription.objects.filter(pending_razorpay_subscription_id=razorpay_subscription_id).first()
    if sub is not None:
        return sub, True
    return None, False


def apply_razorpay_subscription_status(
    razorpay_subscription_id: str,
    rzp_status: str,
    current_end: Any = None,
) -> Subscription | None:
    if not razorpay_subscription_id:
        return None
    sub, _found_via_pending = _subscription_for_razorpay_id(razorpay_subscription_id)
    if sub is None:
        return None
    from django.db import transaction

    with transaction.atomic():
        sub = Subscription.objects.select_for_update().get(pk=sub.pk)
        via_pending = (
            (sub.razorpay_subscription_id or "") != razorpay_subscription_id
            and (sub.pending_razorpay_subscription_id or "") == razorpay_subscription_id
        )
        if via_pending and (rzp_status or "").strip().lower() == "authenticated" and not sub.pending_authenticated_at:
            # The new plan's mandate is approved and its first charge is at the old period's end.
            # End the old subscription at that same cycle end now, so the two never both charge
            # at the renewal (the old one would otherwise renew before the new one goes active).
            sub.pending_authenticated_at = timezone.now()
            sub.save(update_fields=["pending_authenticated_at", "updated_at"])
            old = (sub.razorpay_subscription_id or "").strip()
            if old:
                _cancel_razorpay_subscription(old, at_cycle_end=True)
            return sub
        return _write_razorpay_subscription_status(
            sub, razorpay_subscription_id, rzp_status, current_end, via_pending,
        )


def _write_razorpay_subscription_status(sub, razorpay_subscription_id, rzp_status, current_end, via_pending):
    mapped = _map_razorpay_status(rzp_status)
    if mapped is None:
        return sub
    # A churned tenant stays suspended no matter what Razorpay reports for the
    # old subscription -- not just a re-activation. suspend_for_churn only
    # cancels the remote subscription at cycle end, so it keeps existing (and
    # can still emit e.g. a `halted`/`paused` webhook) until then; none of
    # those should be able to flip status away from the owner's explicit
    # churn decision. The pending (replacement) subscription is allowed to
    # promote once it is actually active.
    if (
        not via_pending
        and sub.status == Subscription.Status.SUSPENDED
        and (sub.churn_reason or "").strip()
    ):
        return sub
    if via_pending and mapped != Subscription.Status.ACTIVE:
        return sub
    previous_status = sub.status
    update_fields = ["status", "updated_at"]
    if via_pending and mapped == Subscription.Status.ACTIVE:
        previous_remote_id = (sub.razorpay_subscription_id or "").strip()
        sub.razorpay_subscription_id = razorpay_subscription_id
        sub.pending_razorpay_subscription_id = ""
        sub.pending_authenticated_at = None
        update_fields.extend(["razorpay_subscription_id", "pending_razorpay_subscription_id", "pending_authenticated_at"])
        if previous_remote_id and previous_remote_id != razorpay_subscription_id:
            _cancel_razorpay_subscription(previous_remote_id, at_cycle_end=True)
    sub.status = mapped
    # BUG-BIL-001: a new past-due cycle must be able to start at step 1.
    if previous_status == Subscription.Status.PAST_DUE and mapped != Subscription.Status.PAST_DUE:
        sub.last_dunning_step = 0
        update_fields.append("last_dunning_step")
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
        # plan the tenant only just started paying for. A renewal of the OLD
        # subscription while a switch is still pending is not that event: it
        # must not hand over the new plan (the first checkout, which has no
        # separate pending id, still promotes on its own activation).
        promote = sub.pending_plan_id and (
            via_pending or not (sub.pending_razorpay_subscription_id or "").strip()
        )
        if promote:
            sub.plan = sub.pending_plan
            sub.pending_plan = None
            update_fields.extend(["plan", "pending_plan"])
        if sub.upgrade_plan_id and (via_pending or sub.plan_id == sub.upgrade_plan_id):
            from .plan_change import clear_upgrade

            clear_upgrade(sub, update_fields)  # WP-BL3: the new plan now has its own subscription
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
    event.attempts = int(event.attempts or 0) + 1
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

