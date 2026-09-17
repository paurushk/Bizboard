"""8.5 / 8.6 — SaaS dunning is not AR dunning; billing recon vs Razorpay."""

from __future__ import annotations

import inspect
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core import mail
from django.test import override_settings
from django.utils import timezone

from billing.models import DeadLetterEvent, Plan, Subscription
from billing.recon import reconcile_saas_subscriptions
from tests.conftest import make_tenant

pytestmark = pytest.mark.django_db


def _past_due_sub(company, **kwargs):
    plan = Plan.objects.create(
        name="Dunn",
        slug=kwargs.pop("slug", "dunn-plan"),
        seat_limit=2,
        modules={},
        price_paise=49900,
    )
    now = timezone.now()
    defaults = {
        "company": company,
        "plan": plan,
        "status": Subscription.Status.PAST_DUE,
        "current_period_end": now - timedelta(days=1),
        "razorpay_subscription_id": "",
    }
    defaults.update(kwargs)
    return Subscription.objects.create(**defaults)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_saas_dunning_emails_owner_and_does_not_call_ar(tenant_a):
    from billing.dunning import run_saas_dunning

    sub = _past_due_sub(tenant_a.company, slug="dunn-a")
    with patch("payments.dunning.run_dunning_all") as ar:
        result = run_saas_dunning()
        ar.assert_not_called()
    assert result["sent"] == 1
    sub.refresh_from_db()
    assert sub.last_dunning_step == 1
    assert sub.last_dunning_at is not None
    assert len(mail.outbox) == 1
    assert "past due" in mail.outbox[0].subject.lower()
    assert tenant_a.owner.email in mail.outbox[0].to


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_saas_dunning_is_idempotent_per_step(tenant_a):
    from billing.dunning import run_saas_dunning

    _past_due_sub(tenant_a.company, slug="dunn-b")
    run_saas_dunning()
    mail.outbox.clear()
    again = run_saas_dunning()
    assert again["sent"] == 0
    assert mail.outbox == []


def test_saas_dunning_skips_active_and_override(tenant_a):
    from billing.dunning import run_saas_dunning

    other = make_tenant("dunn-ovr")
    plan = Plan.objects.create(name="Act", slug="dunn-active", seat_limit=1, modules={}, price_paise=0)
    Subscription.objects.create(
        company=other.company,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        current_period_end=timezone.now() + timedelta(days=10),
    )
    tenant_a.company.billing_override_active = True
    tenant_a.company.save(update_fields=["billing_override_active"])
    _past_due_sub(tenant_a.company, slug="dunn-over")
    result = run_saas_dunning()
    assert result["sent"] == 0


def test_saas_dunning_module_does_not_import_ar():
    import billing.dunning as mod

    src = inspect.getsource(mod)
    imports = [ln.strip() for ln in src.splitlines() if ln.strip().startswith(("import ", "from "))]
    assert all("payments" not in ln for ln in imports)
    assert "run_dunning_all" not in src
    assert "run_dunning_for_company" not in src


def test_beat_keeps_saas_dunning_separate_from_ar():
    from django.conf import settings

    ar = settings.CELERY_BEAT_SCHEDULE["payments-ar-dunning"]["task"]
    saas = settings.CELERY_BEAT_SCHEDULE["billing-saas-dunning"]["task"]
    recon = settings.CELERY_BEAT_SCHEDULE["billing-saas-recon"]["task"]
    assert ar == "payments.tasks.run_ar_dunning_task"
    assert saas == "billing.tasks.run_saas_dunning_task"
    assert recon == "billing.tasks.reconcile_saas_subscriptions_task"
    assert saas != ar


@override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="")
def test_saas_recon_skips_without_keys(tenant_a):
    _past_due_sub(
        tenant_a.company,
        slug="recon-skip",
        razorpay_subscription_id="sub_skip",
        status=Subscription.Status.ACTIVE,
        current_period_end=timezone.now() + timedelta(days=10),
    )
    result = reconcile_saas_subscriptions()
    assert result["skipped"] is True
    assert result["checked"] == 0
    assert DeadLetterEvent.objects.filter(provider="billing_recon").count() == 0


@override_settings(RAZORPAY_KEY_ID="rzp_test", RAZORPAY_KEY_SECRET="secret")
def test_saas_recon_skips_in_test_env_without_flag(tenant_a):
    _past_due_sub(
        tenant_a.company,
        slug="recon-testenv",
        razorpay_subscription_id="sub_testenv",
        status=Subscription.Status.ACTIVE,
        current_period_end=timezone.now() + timedelta(days=10),
    )
    with patch("billing.recon.fetch_razorpay_subscription") as fetch:
        result = reconcile_saas_subscriptions()
        fetch.assert_not_called()
    assert result["skipped"] is True
    assert result["reason"] == "test_env"


@override_settings(RAZORPAY_KEY_ID="rzp_test", RAZORPAY_KEY_SECRET="secret", BILLING_RECON_IN_TESTS=True)
def test_saas_recon_applies_mismatch_without_dlq_noise(tenant_a):
    """A drift that recon successfully corrects must NOT be parked -- the DLQ
    is a "needs action" queue, and parking every self-healed mismatch there
    buries genuine unresolved failures under routine corrections. The audit
    log (asserted via the applied status below) is the durable record."""
    sub = _past_due_sub(
        tenant_a.company,
        slug="recon-mis",
        razorpay_subscription_id="sub_mis",
        status=Subscription.Status.ACTIVE,
        current_period_end=timezone.now() + timedelta(days=10),
    )
    remote = {"id": "sub_mis", "status": "halted", "current_end": None}
    with patch("billing.recon.fetch_razorpay_subscription", return_value=remote):
        result = reconcile_saas_subscriptions()
    assert result["skipped"] is False
    assert result["mismatches"] == 1
    sub.refresh_from_db()
    assert sub.status == Subscription.Status.PAST_DUE
    assert DeadLetterEvent.objects.filter(provider="billing_recon").count() == 0


@override_settings(RAZORPAY_KEY_ID="rzp_test", RAZORPAY_KEY_SECRET="secret", BILLING_RECON_IN_TESTS=True)
def test_saas_recon_fetch_error_parks_dlq(tenant_a):
    _past_due_sub(
        tenant_a.company,
        slug="recon-err",
        razorpay_subscription_id="sub_err",
        status=Subscription.Status.ACTIVE,
        current_period_end=timezone.now() + timedelta(days=10),
    )
    with patch("billing.recon.fetch_razorpay_subscription", side_effect=RuntimeError("timeout")):
        result = reconcile_saas_subscriptions()
    assert result["mismatches"] == 1
    assert DeadLetterEvent.objects.filter(provider="billing_recon").exists()


def test_park_dead_letter_dedupes_concurrent_pending_rows(tenant_a):
    """billing_dlq_uniq_pending_provider_event closes the check-then-create
    race: a second parker for the same provider/event_id while the first is
    still PENDING must get the existing row back, not a duplicate."""
    from billing.services import park_dead_letter

    first = park_dead_letter(
        provider="billing_recon", event_id="recon:1:halted", payload={}, error="first", company=tenant_a.company,
    )
    second = park_dead_letter(
        provider="billing_recon", event_id="recon:1:halted", payload={}, error="second", company=tenant_a.company,
    )
    assert second.pk == first.pk
    assert DeadLetterEvent.objects.filter(provider="billing_recon", event_id="recon:1:halted").count() == 1


def test_chargeback_event_without_subscription_is_ignored():
    """8.8 — Razorpay dispute/chargeback shapes without a subscription entity are ignored."""
    from rest_framework.test import APIClient

    client = APIClient()
    resp = client.post(
        "/api/v1/billing/razorpay/webhook/",
        {
            "event": "payment.dispute.created",
            "payload": {"payment": {"entity": {"id": "pay_cb_1", "status": "disputed"}}},
        },
        format="json",
        HTTP_X_BIZBOARD_TEST_WEBHOOK="1",
    )
    assert resp.status_code == 200, resp.data
    assert resp.data.get("ignored") is True
    assert DeadLetterEvent.objects.filter(provider="razorpay_subscription").count() == 0


def test_chargeback_path_does_not_invoke_ar_dunning():
    from rest_framework.test import APIClient

    client = APIClient()
    with patch("payments.dunning.run_dunning_all") as ar:
        resp = client.post(
            "/api/v1/billing/razorpay/webhook/",
            {
                "event": "refund.processed",
                "payload": {"refund": {"entity": {"id": "rfnd_1"}}},
            },
            format="json",
            HTTP_X_BIZBOARD_TEST_WEBHOOK="1",
        )
        assert resp.status_code == 200
        ar.assert_not_called()


def test_saas_recon_module_is_not_collections_recon():
    import billing.recon as mod

    src = inspect.getsource(mod)
    imports = [ln.strip() for ln in src.splitlines() if ln.strip().startswith(("import ", "from "))]
    assert all("payments.services" not in ln and "reconcile_gateway_captures" not in ln for ln in imports)
