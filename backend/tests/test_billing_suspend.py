"""SET-06: suspending a workspace is guarded, audited, and replaying parked events is operator work."""

import pytest
from django.contrib import admin
from django.core.cache import cache

from billing.admin import DeadLetterEventAdmin
from billing.models import DeadLetterEvent, Plan, Subscription
from billing.services import start_or_update_subscription
from core.models import AuditEvent

URL = "/api/v1/billing/subscription/"
PASSWORD = "StrongPass123!"


@pytest.fixture(autouse=True)
def _fresh_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def subscribed(tenant_a):
    plan = Plan.objects.create(name="Starter", slug="starter-set06", price_paise=49900, seat_limit=5)
    start_or_update_subscription(company=tenant_a.company, plan=plan)
    Subscription.objects.filter(company=tenant_a.company).update(status=Subscription.Status.ACTIVE)
    return tenant_a


def _suspend(tenant, **overrides):
    body = {
        "action": "suspend",
        "churn_reason": "Closing the shop",
        "confirm_company_name": tenant.company.name,
        "password": PASSWORD,
    }
    body.update(overrides)
    return tenant.client.post(URL, body, format="json")


def _status(tenant):
    return Subscription.objects.get(company=tenant.company).status


def test_a_complete_request_suspends_and_is_audited(subscribed):
    r = _suspend(subscribed)
    assert r.status_code == 200, r.data
    assert _status(subscribed) == Subscription.Status.SUSPENDED
    event = AuditEvent.objects.get(company=subscribed.company, action="billing.suspend")
    assert event.description == "Closing the shop" and event.user_id == subscribed.owner.id


@pytest.mark.parametrize(
    "overrides,needle",
    [
        ({"churn_reason": "  "}, "reason"),
        ({"confirm_company_name": ""}, "company name"),
        ({"confirm_company_name": "Some Other Shop"}, "company name"),
    ],
)
def test_reason_and_typed_company_name_are_required(subscribed, overrides, needle):
    r = _suspend(subscribed, **overrides)
    assert r.status_code == 400 and needle in str(r.data).lower()
    assert _status(subscribed) == Subscription.Status.ACTIVE


def test_company_name_match_ignores_case_and_extra_spaces(subscribed):
    name = "  " + subscribed.company.name.upper().replace(" ", "   ") + " "
    assert _suspend(subscribed, confirm_company_name=name).status_code == 200


def test_the_password_is_required_and_checked(subscribed):
    assert _suspend(subscribed, password="").status_code == 400
    r = _suspend(subscribed, password="not-the-password")
    assert r.status_code == 400 and "password" in str(r.data).lower()
    assert _status(subscribed) == Subscription.Status.ACTIVE
    assert not AuditEvent.objects.filter(company=subscribed.company, action="billing.suspend").exists()


def test_wrong_passwords_are_counted_and_lock_the_action(subscribed):
    for _ in range(5):
        assert _suspend(subscribed, password="nope").status_code == 400
    locked = _suspend(subscribed)  # even the right password is refused for a while
    assert locked.status_code == 400 and "too many" in str(locked.data).lower()
    assert _status(subscribed) == Subscription.Status.ACTIVE


def test_a_right_password_clears_the_failure_count(subscribed):
    for _ in range(4):
        _suspend(subscribed, password="nope")
    assert _suspend(subscribed).status_code == 200


def test_a_two_step_code_is_required_when_the_owner_has_one(subscribed, monkeypatch):
    from accounts.models import UserMfa
    from django.utils import timezone

    UserMfa.objects.create(user=subscribed.owner, secret_enc="x", confirmed_at=timezone.now())
    monkeypatch.setattr("accounts.mfa_service.check_second_factor", lambda rec, **kw: kw.get("code") == "123456")
    refused = _suspend(subscribed)
    assert refused.status_code == 400 and "code" in str(refused.data).lower()
    assert _status(subscribed) == Subscription.Status.ACTIVE
    assert _suspend(subscribed, code="123456").status_code == 200


def test_an_owner_without_a_password_is_told_to_set_one(subscribed):
    subscribed.owner.set_unusable_password()
    subscribed.owner.save()
    r = _suspend(subscribed)
    assert r.status_code == 400 and "password" in str(r.data).lower()


def test_suspending_twice_is_refused_and_not_audited_twice(subscribed):
    assert _suspend(subscribed).status_code == 200
    again = _suspend(subscribed)
    assert again.status_code == 400 and "already suspended" in str(again.data).lower()
    assert AuditEvent.objects.filter(company=subscribed.company, action="billing.suspend").count() == 1


def test_staff_cannot_suspend(subscribed):
    r = subscribed.staff_client.post(
        URL, {"action": "suspend", "churn_reason": "x", "confirm_company_name": "x", "password": PASSWORD}, format="json"
    )
    assert r.status_code == 403


def test_the_admin_can_replay_pending_parked_events_only(subscribed, monkeypatch):
    replayed = []
    monkeypatch.setattr("billing.services.replay_dead_letter", lambda event, user=None: replayed.append(event.pk))
    pending = DeadLetterEvent.objects.create(company=subscribed.company, provider="razorpay", event_id="e1")
    done = DeadLetterEvent.objects.create(
        company=subscribed.company, provider="razorpay", event_id="e2", status=DeadLetterEvent.Status.REPLAYED
    )
    model_admin = DeadLetterEventAdmin(DeadLetterEvent, admin.site)
    messages = []
    monkeypatch.setattr(model_admin, "message_user", lambda request, msg, level=None: messages.append(str(msg)))
    request = type("R", (), {"user": subscribed.owner})()
    model_admin.replay_selected(request, DeadLetterEvent.objects.filter(pk__in=[pending.pk, done.pk]))
    assert replayed == [pending.pk]
    assert messages == ["Replayed 1; 0 failed; 1 not pending."]
    assert "replay_selected" in model_admin.actions
