"""WP-BL3 (proration on plan change) and WP-BL4 (UPI Autopay renewals)."""

import hashlib
import hmac
import json
from datetime import timedelta
from unittest import mock

import pytest
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from billing.autopay import send_renewal_reminders
from billing.models import DeadLetterEvent, Plan, PlatformGstInvoice, Subscription
from billing.plan_change import effective_plan, proration_paise, revert_unpaid_upgrades
from billing.quotas import usage_snapshot
from billing.services import apply_razorpay_subscription_status, plan_modules_for_company, start_or_update_subscription
from core.exceptions import BusinessRuleError

pytestmark = pytest.mark.django_db
_SECRET = "bl34-secret"
URL = "/api/v1/billing/razorpay/webhook/"
KEYS = {"RAZORPAY_KEY_ID": "rzp_test_key", "RAZORPAY_KEY_SECRET": "rzp_test_secret"}


@pytest.fixture(autouse=True)
def _clean():
    cache.clear()
    yield
    cache.clear()


def _plans():
    basic = Plan.objects.create(name="Basic", slug="basic-bl3", price_paise=50000, seat_limit=2,
                                modules={"ENABLE_CRM": False}, razorpay_plan_id="plan_basic")
    pro = Plan.objects.create(name="Pro", slug="pro-bl3", price_paise=110000, seat_limit=10,
                              modules={"ENABLE_CRM": True}, razorpay_plan_id="plan_pro")
    return basic, pro


def _live(tenant, plan, *, days_left=15):
    return Subscription.objects.update_or_create(
        company=tenant.company,
        defaults={"plan": plan, "status": Subscription.Status.ACTIVE, "razorpay_subscription_id": "sub_old",
                  "current_period_end": timezone.now() + timedelta(days=days_left)},
    )[0]


def _post(payload, event_id):
    body = json.dumps(payload).encode()
    sig = hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return APIClient().post(URL, data=body, content_type="application/json",
                            HTTP_X_RAZORPAY_SIGNATURE=sig, HTTP_X_RAZORPAY_EVENT_ID=event_id)


# --- WP-BL3 ---------------------------------------------------------------------------------


def test_proration_amount_on_fixed_dates():
    now = timezone.now()
    assert proration_paise(old_price=50000, new_price=110000, period_end=now + timedelta(days=15), now=now) == 30000
    assert proration_paise(old_price=50000, new_price=110000, period_end=now + timedelta(days=30), now=now) == 60000
    assert proration_paise(old_price=110000, new_price=50000, period_end=now + timedelta(days=15), now=now) == 0
    assert proration_paise(old_price=50000, new_price=110000, period_end=now - timedelta(days=1), now=now) == 0


@override_settings(**KEYS)
def test_upgrade_applies_now_charges_the_difference_once_and_starts_the_new_plan_at_period_end(tenant_a):
    basic, pro = _plans()
    sub = _live(tenant_a, basic)
    with mock.patch("billing.services._create_razorpay_subscription", return_value=("sub_new", "https://rzp/mandate")) as create, \
            mock.patch("billing.plan_change._create_payment_link", return_value=("plink_1", "https://rzp/pay")) as link:
        sub, _ = start_or_update_subscription(company=tenant_a.company, plan=pro)
    assert create.call_args.kwargs["start_at"] == int(sub.current_period_end.timestamp())
    assert link.call_args.kwargs["amount_paise"] == 30000
    assert sub._proration_url == "https://rzp/pay"
    sub.refresh_from_db()
    assert sub.plan_id == basic.pk and sub.pending_plan_id == pro.pk and sub.upgrade_plan_id == pro.pk
    assert effective_plan(sub) == pro
    assert plan_modules_for_company(tenant_a.company) == {"ENABLE_CRM": True}
    assert usage_snapshot(tenant_a.company)["seats"]["limit"] == 10

    paid = {"event": "payment_link.paid", "payload": {
        "payment_link": {"entity": {"id": "plink_1", "amount": 30000, "amount_paid": 30000}},
        "payment": {"entity": {"id": "pay_pr_1", "amount": 30000, "status": "captured"}}}}
    with override_settings(RAZORPAY_WEBHOOK_SECRET=_SECRET):
        assert _post(paid, "evt_pl_1").status_code == 200
        assert _post(paid, "evt_pl_2").status_code == 200  # redelivery
    assert PlatformGstInvoice.objects.filter(company=tenant_a.company, capture_id="pay_pr_1").count() == 1
    sub.refresh_from_db()
    assert sub.proration_paid_at is not None

    # The new subscription starts at period end: plan switches, the overlay goes.
    with mock.patch("billing.services._cancel_razorpay_subscription"):
        done = apply_razorpay_subscription_status("sub_new", "active")
    assert done.plan_id == pro.pk and done.upgrade_plan_id is None


@override_settings(**KEYS)
def test_unpaid_upgrade_reverts_after_the_grace(tenant_a):
    basic, pro = _plans()
    _live(tenant_a, basic)
    with mock.patch("billing.services._create_razorpay_subscription", return_value=("sub_new2", "")), \
            mock.patch("billing.plan_change._create_payment_link", return_value=("plink_2", "")):
        start_or_update_subscription(company=tenant_a.company, plan=pro)
    assert revert_unpaid_upgrades() == 0  # still inside the grace
    with mock.patch("billing.services._cancel_razorpay_subscription", return_value=True) as cancel, \
            mock.patch("billing.plan_change._payment_link_status", return_value="created"):
        assert revert_unpaid_upgrades(now=timezone.now() + timedelta(days=4)) == 1
    cancel.assert_called_once_with("sub_new2", at_cycle_end=False)
    sub = Subscription.objects.get(company=tenant_a.company)
    assert sub.upgrade_plan_id is None and sub.pending_plan_id is None and effective_plan(sub) == basic


@override_settings(**KEYS)
def test_downgrade_waits_for_period_end_and_is_refused_over_quota(tenant_a):
    from accounts.models import CompanyUser, User

    basic, pro = _plans()
    _live(tenant_a, pro)
    for i in range(3):
        u = User.objects.create_user(email=f"seat{i}@bl3.test", password="x-Strong-pass-1")
        CompanyUser.objects.create(company=tenant_a.company, user=u, role=CompanyUser.Role.SALES_STAFF)
    with mock.patch("billing.services._create_razorpay_subscription", return_value=("sub_down", "")):
        with pytest.raises(BusinessRuleError, match="remove"):
            start_or_update_subscription(company=tenant_a.company, plan=basic)
    CompanyUser.objects.filter(company=tenant_a.company, user__email__endswith="@bl3.test").update(is_active=False)
    with mock.patch("billing.services._create_razorpay_subscription", return_value=("sub_down", "")), \
            mock.patch("billing.plan_change._create_payment_link") as link:
        sub, _ = start_or_update_subscription(company=tenant_a.company, plan=basic)
    link.assert_not_called()  # nothing to charge on a downgrade
    sub.refresh_from_db()
    assert sub.plan_id == pro.pk and sub.pending_plan_id == basic.pk and effective_plan(sub) == pro


# --- WP-BL4 ---------------------------------------------------------------------------------


@override_settings(RAZORPAY_WEBHOOK_SECRET=_SECRET, BILLING_WEBHOOK_MAX_AGE_SECONDS=0)
@pytest.mark.parametrize("event,status,mandate,local", [
    ("subscription.authenticated", "authenticated", "AUTHENTICATED", Subscription.Status.ACTIVE),
    ("subscription.halted", "halted", "HALTED", Subscription.Status.PAST_DUE),
    ("subscription.paused", "paused", "PAUSED", Subscription.Status.PAST_DUE),
    ("subscription.resumed", "active", "ACTIVE", Subscription.Status.ACTIVE),
    ("subscription.cancelled", "cancelled", "CANCELLED", Subscription.Status.SUSPENDED),
])
def test_mandate_events(tenant_a, event, status, mandate, local):
    basic, _ = _plans()
    _live(tenant_a, basic)
    payload = {"event": event, "payload": {"subscription": {"entity": {"id": "sub_old", "status": status}}}}
    assert _post(payload, f"evt_{event}").status_code == 200
    sub = Subscription.objects.get(company=tenant_a.company)
    assert sub.mandate_status == mandate and sub.status == local
    # Replay is a no-op.
    assert _post(payload, f"evt_{event}").json()["data"].get("duplicate") is True


@override_settings(RAZORPAY_WEBHOOK_SECRET=_SECRET, BILLING_WEBHOOK_MAX_AGE_SECONDS=0)
def test_upi_charge_records_the_method_and_unknown_events_are_parked(tenant_a):
    basic, _ = _plans()
    _live(tenant_a, basic)
    charged = {"event": "subscription.charged", "payload": {
        "subscription": {"entity": {"id": "sub_old", "status": "active"}},
        "payment": {"entity": {"id": "pay_upi_1", "amount": 50000, "status": "captured", "method": "upi"}}}}
    assert _post(charged, "evt_c1").status_code == 200
    assert Subscription.objects.get(company=tenant_a.company).payment_method == "upi"
    # An event we don't handle is parked before it is applied: it must not change the status.
    odd = {"event": "subscription.weird_new_event",
           "payload": {"subscription": {"entity": {"id": "sub_old", "status": "halted"}}}}
    assert _post(odd, "evt_odd").status_code == 200
    assert DeadLetterEvent.objects.filter(error__icontains="subscription.weird_new_event").exists()
    assert Subscription.objects.get(company=tenant_a.company).status == Subscription.Status.ACTIVE
    # subscription.updated is a real Razorpay event: applied, not parked.
    updated = {"event": "subscription.updated", "payload": {"subscription": {"entity": {"id": "sub_old", "status": "active"}}}}
    assert _post(updated, "evt_upd").status_code == 200
    assert not DeadLetterEvent.objects.filter(error__icontains="subscription.updated").exists()


def test_renewal_reminder_is_one_email_per_cycle_and_never_sms(tenant_a):
    basic, _ = _plans()
    tenant_a.company.email = "owner@bl4.test"
    tenant_a.company.save(update_fields=["email"])
    sub = _live(tenant_a, basic, days_left=3)
    sub.payment_method = "upi"
    sub.save(update_fields=["payment_method"])
    mail.outbox.clear()
    with mock.patch("core.services.sms.SmsProvider.send_template") as sms:
        assert send_renewal_reminders() == 1
        assert send_renewal_reminders() == 0
    sms.assert_not_called()
    assert len(mail.outbox) == 1 and "UPI Autopay" in mail.outbox[0].body


# --- review fixes ----------------------------------------------------------------------------


@override_settings(**KEYS)
def test_choosing_the_upgrade_plan_again_reuses_the_link_and_charges_nothing_new(tenant_a):
    basic, pro = _plans()
    _live(tenant_a, basic)
    with mock.patch("billing.services._create_razorpay_subscription", return_value=("sub_up", "")), \
            mock.patch("billing.plan_change._create_payment_link", return_value=("plink_a", "https://rzp.io/l/a")):
        start_or_update_subscription(company=tenant_a.company, plan=pro)
    with mock.patch("billing.services._create_razorpay_subscription") as created, \
            mock.patch("billing.plan_change._create_payment_link") as link, \
            mock.patch("billing.services.fetch_razorpay_subscription", return_value={"short_url": "https://rzp.io/i/m"}):
        sub, _ = start_or_update_subscription(company=tenant_a.company, plan=pro)
    created.assert_not_called()
    link.assert_not_called()
    assert sub._proration_url == "https://rzp.io/l/a"
    sub.refresh_from_db()
    assert sub.proration_link_id == "plink_a" and sub.proration_paid_at is None


@override_settings(**KEYS)
def test_another_plan_is_refused_while_an_upgrade_waits_and_the_old_plan_undoes_it(tenant_a):
    basic, pro = _plans()
    ent = Plan.objects.create(name="Ent", slug="ent-bl3", price_paise=300000, seat_limit=50,
                              modules={}, razorpay_plan_id="plan_ent")
    _live(tenant_a, basic)
    with mock.patch("billing.services._create_razorpay_subscription", return_value=("sub_up2", "")), \
            mock.patch("billing.plan_change._create_payment_link", return_value=("plink_b", "")):
        start_or_update_subscription(company=tenant_a.company, plan=pro)
    with pytest.raises(BusinessRuleError, match="waiting for its payment"):
        start_or_update_subscription(company=tenant_a.company, plan=ent)
    with mock.patch("billing.services._cancel_razorpay_subscription", return_value=True) as cancel, \
            mock.patch("billing.plan_change._cancel_payment_link") as cancel_link:
        start_or_update_subscription(company=tenant_a.company, plan=basic)
    cancel.assert_called_once_with("sub_up2", at_cycle_end=False)
    cancel_link.assert_called_once_with("plink_b")
    sub = Subscription.objects.get(company=tenant_a.company)
    assert sub.upgrade_plan_id is None and sub.pending_plan_id is None and effective_plan(sub) == basic


@override_settings(**KEYS)
def test_old_subscription_renewal_does_not_hand_over_the_pending_plan(tenant_a):
    basic, pro = _plans()
    _live(tenant_a, pro)
    sub = Subscription.objects.get(company=tenant_a.company)
    sub.pending_plan = basic
    sub.pending_razorpay_subscription_id = "sub_down_pending"
    sub.save()
    done = apply_razorpay_subscription_status("sub_old", "active")  # the OLD one renewed
    assert done.plan_id == pro.pk and done.pending_plan_id == basic.pk
    with mock.patch("billing.services._cancel_razorpay_subscription", return_value=True):
        done = apply_razorpay_subscription_status("sub_down_pending", "active")
    assert done.plan_id == basic.pk and done.pending_plan_id is None


@override_settings(**KEYS)
def test_new_mandate_approval_ends_the_old_subscription_at_its_cycle_end(tenant_a):
    basic, pro = _plans()
    _live(tenant_a, pro)
    sub = Subscription.objects.get(company=tenant_a.company)
    sub.pending_plan = basic
    sub.pending_razorpay_subscription_id = "sub_next"
    sub.save()
    with mock.patch("billing.services._cancel_razorpay_subscription", return_value=True) as cancel:
        apply_razorpay_subscription_status("sub_next", "authenticated")
        apply_razorpay_subscription_status("sub_next", "authenticated")  # redelivered
    cancel.assert_called_once_with("sub_old", at_cycle_end=True)
    sub.refresh_from_db()
    assert sub.pending_authenticated_at is not None and sub.plan_id == pro.pk


@override_settings(**KEYS)
def test_a_paid_upgrade_lapses_after_its_period_when_the_new_plan_never_starts(tenant_a):
    basic, pro = _plans()
    _live(tenant_a, basic, days_left=10)
    with mock.patch("billing.services._create_razorpay_subscription", return_value=("sub_up3", "")), \
            mock.patch("billing.plan_change._create_payment_link", return_value=("plink_c", "")):
        start_or_update_subscription(company=tenant_a.company, plan=pro)
    from billing.plan_change import handle_payment_link_event

    handle_payment_link_event({"event": "payment_link.paid", "payload": {
        "payment_link": {"entity": {"id": "plink_c"}},
        "payment": {"entity": {"id": "pay_c", "amount": 20000}}}})
    sub = Subscription.objects.get(company=tenant_a.company)
    assert effective_plan(sub) == pro
    later = timezone.now() + timedelta(days=14)  # period end (10 days) + the 3-day grace has passed
    with mock.patch("django.utils.timezone.now", return_value=later):
        assert effective_plan(Subscription.objects.get(company=tenant_a.company)) == basic


@override_settings(**KEYS)
def test_a_paid_link_that_matches_no_upgrade_is_invoiced_and_parked(tenant_a):
    from billing.plan_change import handle_payment_link_event

    out = handle_payment_link_event({"event": "payment_link.paid", "payload": {
        "payment_link": {"entity": {"id": "plink_orphan", "notes": {"company_id": str(tenant_a.company.pk)}}},
        "payment": {"entity": {"id": "pay_orphan", "amount": 30000}}}})
    assert out.get("parked") is True
    assert PlatformGstInvoice.objects.filter(company=tenant_a.company, capture_id="pay_orphan").exists()
    assert DeadLetterEvent.objects.filter(provider="razorpay_payment_link").exists()


@override_settings(**KEYS)
def test_an_upgrade_seat_limit_applies_to_invites_at_once(tenant_a):
    from accounts.views import _enforce_plan_seat_limit

    basic, pro = _plans()
    basic.seat_limit = 1
    basic.save(update_fields=["seat_limit"])
    _live(tenant_a, basic)
    with pytest.raises(Exception):
        _enforce_plan_seat_limit(tenant_a.company)
    with mock.patch("billing.services._create_razorpay_subscription", return_value=("sub_up4", "")), \
            mock.patch("billing.plan_change._create_payment_link", return_value=("plink_d", "")):
        start_or_update_subscription(company=tenant_a.company, plan=pro)
    _enforce_plan_seat_limit(tenant_a.company)  # Pro's 10 seats apply during the upgrade
