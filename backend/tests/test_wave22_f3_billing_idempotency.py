"""Wave 22 Sprint F3 — billing gate, seats, idempotency placeholder."""

from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.exceptions import APIException

from accounts.models import CompanyUser
from billing.models import Plan, Subscription
from billing.services import company_writes_blocked, start_or_update_subscription
from core.idempotency import (
    IdempotencyInFlightError,
    begin_record,
    get_record,
    store_record,
)
from core.models import IdempotencyRecord
from rest_framework.response import Response

pytestmark = pytest.mark.django_db


def _plan(**kwargs):
    defaults = {
        "name": "Starter",
        "slug": kwargs.pop("slug", "f3-starter"),
        "seat_limit": 2,
        "modules": {},
        "price_paise": 49900,
    }
    defaults.update(kwargs)
    return Plan.objects.create(**defaults)


@override_settings(REQUIRE_SUBSCRIPTION=True)
def test_bb_000725_require_subscription_blocks_when_no_sub(tenant_a):
    assert Subscription.objects.filter(company=tenant_a.company).count() == 0
    assert company_writes_blocked(tenant_a.company) is True

    tenant_a.company.billing_override_active = True
    tenant_a.company.save(update_fields=["billing_override_active"])
    assert company_writes_blocked(tenant_a.company) is False


@override_settings(REQUIRE_SUBSCRIPTION=False, RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="")
def test_bb_000725_checkout_without_razorpay_does_not_brick_tenant(tenant_a):
    # BB-000671 decision (see test_bb_000671_owner_plans_checkout_portal):
    # when Razorpay is not configured at all, a stub checkout must NOT leave the
    # tenant PENDING (which blocks all writes) — it grants a time-boxed TRIAL so
    # a self-hosted / pre-payment tenant can keep working.
    plan = _plan(slug="f3-pending")
    sub, _order = start_or_update_subscription(company=tenant_a.company, plan=plan)
    assert sub.status == Subscription.Status.TRIAL
    assert company_writes_blocked(tenant_a.company) is False


@override_settings(BILLING_PAST_DUE_GRACE_DAYS=0)
def test_bb_000726_past_due_blocks_writes(tenant_a):
    plan = _plan(slug="f3-past-due")
    Subscription.objects.create(
        company=tenant_a.company,
        plan=plan,
        status=Subscription.Status.PAST_DUE,
        current_period_end=timezone.now() - timedelta(days=1),
    )
    assert company_writes_blocked(tenant_a.company) is True


@override_settings(BILLING_PAST_DUE_GRACE_DAYS=7)
def test_bb_000726_past_due_within_grace_allows_writes(tenant_a):
    plan = _plan(slug="f3-grace")
    Subscription.objects.create(
        company=tenant_a.company,
        plan=plan,
        status=Subscription.Status.PAST_DUE,
        current_period_end=timezone.now() - timedelta(days=1),
    )
    assert company_writes_blocked(tenant_a.company) is False


def test_bb_000727_seat_limit_rejects_invite(tenant_a):
    # tenant_a already has owner + staff (2 active). seat_limit=2 → next invite fails.
    plan = _plan(slug="f3-seats", seat_limit=2)
    Subscription.objects.create(
        company=tenant_a.company,
        plan=plan,
        status=Subscription.Status.ACTIVE,
    )
    assert CompanyUser.objects.filter(company=tenant_a.company, is_active=True).count() == 2

    resp = tenant_a.client.post(
        "/api/v1/company/users/",
        {
            "email": "extra.seat@alpha.test",
            "password": "StrongPass123!",
            "role": "SALES_STAFF",
        },
        format="json",
    )
    assert resp.status_code == 400, resp.data
    assert "seat" in str(resp.data).lower() or "limit" in str(resp.data).lower()


def test_bb_000730_idempotency_inflight_placeholder_conflict(tenant_a):
    """Concurrent-ish: second begin while first still in-flight → 409."""
    company = tenant_a.company
    scope = "sales_invoice_create"
    key = "f3-inflight-key"

    first = begin_record(company=company, scope=scope, raw_key=key)
    assert isinstance(first, IdempotencyRecord)
    assert first.status_code == 0

    with pytest.raises(IdempotencyInFlightError) as exc:
        begin_record(company=company, scope=scope, raw_key=key)
    assert isinstance(exc.value, APIException)
    assert exc.value.status_code == 409

    store_record(
        company=company,
        scope=scope,
        raw_key=key,
        response=Response({"id": 42}, status=201),
        resource_id="42",
    )
    row = get_record(company=company, scope=scope, raw_key=key)
    assert row is not None
    assert row.status_code == 201
    assert row.resource_id == "42"

    replayed = begin_record(company=company, scope=scope, raw_key=key)
    assert isinstance(replayed, Response)
    assert replayed.status_code == 201
    assert replayed.data["id"] == 42


def test_stale_inflight_idempotency_record_is_replaced(tenant_a):
    company = tenant_a.company
    # B6-014: "sales_invoice_create" used to stand in here as an arbitrary
    # non-money scope, but it's a real scope name that belongs in (and, after
    # B6-014, now is in) MONEY_IDEMPOTENCY_SCOPES — using it made this test
    # exercise the exact stale-reclaim gap B6-014 closed. A scope genuinely
    # outside the money set is what this test is actually about.
    scope = "some_non_money_scope"
    key = "f3-stale-key"
    first = begin_record(company=company, scope=scope, raw_key=key)
    assert isinstance(first, IdempotencyRecord)
    IdempotencyRecord.objects.filter(pk=first.pk).update(
        created_at=timezone.now() - timedelta(minutes=16),
    )
    second = begin_record(company=company, scope=scope, raw_key=key)
    assert isinstance(second, IdempotencyRecord)
    assert second.pk != first.pk
    assert not IdempotencyRecord.objects.filter(pk=first.pk).exists()


def test_stale_inflight_money_scope_is_not_reclaimed(tenant_a):
    """B6-014: a money-creating scope must stay claimed past the 15-min stale
    window — the first request may still legitimately be committing (a large
    import commit, a slow invoice complete). Reclaiming it lets a client retry
    double-run the same non-idempotent-by-construction operation."""
    company = tenant_a.company
    scope = "sales_invoice_create"
    key = "f3-money-stale-key"
    first = begin_record(company=company, scope=scope, raw_key=key)
    assert isinstance(first, IdempotencyRecord)
    IdempotencyRecord.objects.filter(pk=first.pk).update(
        created_at=timezone.now() - timedelta(minutes=16),
    )
    with pytest.raises(IdempotencyInFlightError):
        begin_record(company=company, scope=scope, raw_key=key)
    assert IdempotencyRecord.objects.filter(pk=first.pk).exists()


@override_settings(RAZORPAY_KEY_ID="rzp_test_key", RAZORPAY_KEY_SECRET="rzp_test_secret")
def test_b9_005_live_plan_switch_defers_to_next_cycle_no_proration(tenant_a):
    """B9-005: an already-live paying subscriber changing plans must not be
    charged for the new plan immediately while the old one is still also
    billing through its cancel-at-cycle-end window. The switch is deferred:
    the new Razorpay subscription is scheduled to start_at the current
    period's end, and `plan`/entitlements stay on the old (already paid for)
    plan until the webhook confirms the new one actually started."""
    from unittest.mock import patch

    old_plan = _plan(slug="b9005-old", razorpay_plan_id="rzp_plan_old")
    new_plan = _plan(slug="b9005-new", razorpay_plan_id="rzp_plan_new")
    period_end = timezone.now() + timedelta(days=12)
    sub = Subscription.objects.create(
        company=tenant_a.company,
        plan=old_plan,
        status=Subscription.Status.ACTIVE,
        razorpay_subscription_id="rzp_sub_old",
        current_period_end=period_end,
    )

    with (
        patch("billing.services._create_razorpay_subscription", return_value="rzp_sub_new") as create_mock,
        patch("billing.services._cancel_razorpay_subscription") as cancel_mock,
    ):
        updated, order_id = start_or_update_subscription(company=tenant_a.company, plan=new_plan)

    # The new subscription was scheduled to start exactly at the old one's
    # period end -- not immediately (no double-billing window).
    create_mock.assert_called_once()
    assert create_mock.call_args.kwargs.get("start_at") == int(period_end.timestamp())
    cancel_mock.assert_called_once_with("rzp_sub_old", at_cycle_end=True)

    updated.refresh_from_db()
    assert order_id == "rzp_sub_new"
    assert updated.razorpay_subscription_id == "rzp_sub_new"
    # Deferred: still on the old plan (what the tenant already paid for) and
    # still ACTIVE -- no proration charge, no premature entitlement change.
    assert updated.plan_id == old_plan.pk
    assert updated.status == Subscription.Status.ACTIVE
    assert updated.pending_plan_id == new_plan.pk

    # Webhook confirms the new subscription actually started billing.
    from billing.services import apply_razorpay_subscription_status

    confirmed = apply_razorpay_subscription_status(
        "rzp_sub_new", "active", current_end=int((period_end + timedelta(days=30)).timestamp())
    )
    assert confirmed.plan_id == new_plan.pk
    assert confirmed.pending_plan_id is None


@override_settings(RAZORPAY_KEY_ID="rzp_test_key", RAZORPAY_KEY_SECRET="rzp_test_secret")
def test_b9_005_fresh_subscription_still_switches_immediately(tenant_a):
    """A brand-new subscriber (no live prior plan to protect) keeps the
    existing immediate-switch behavior -- deferral only applies when there is
    something already paid-for to avoid double-charging."""
    from unittest.mock import patch

    plan = _plan(slug="b9005-fresh", razorpay_plan_id="rzp_plan_fresh")

    with (
        patch("billing.services._create_razorpay_subscription", return_value="rzp_sub_fresh") as create_mock,
        patch("billing.services._cancel_razorpay_subscription"),
    ):
        sub, _order = start_or_update_subscription(company=tenant_a.company, plan=plan)

    assert create_mock.call_args.kwargs.get("start_at") is None
    assert sub.plan_id == plan.pk
    assert sub.pending_plan_id is None
