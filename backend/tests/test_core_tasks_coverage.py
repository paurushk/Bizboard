"""Branch coverage for core/tasks.py — the retention + notification tasks that
back celery-beat. (celery_beat_heartbeat / basic send are in test_wave14_p0 /
test_next_batch_smtp_gsp; this hits the skip / fail-closed / prune branches.)
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone

pytestmark = pytest.mark.django_db


# --- send_email_notification --------------------------------------------------

def _notification(tenant, **kw):
    from core.models import Notification

    defaults = dict(
        company=tenant.company, channel=Notification.Channel.EMAIL,
        recipient="a@b.test", subject="Hi", body="Body",
        status=Notification.Status.QUEUED,
    )
    defaults.update(kw)
    return Notification.objects.create(**defaults)


def test_send_email_skips_when_a_send_is_already_in_flight(tenant_a):
    from core.models import Notification
    from core.tasks import send_email_notification

    n = _notification(tenant_a)
    cache.add(f"bizboard:email_send:{n.id}", "1", timeout=180)  # someone else holds the lock
    try:
        send_email_notification(n.id)
    finally:
        cache.delete(f"bizboard:email_send:{n.id}")
    n.refresh_from_db()
    assert n.status == Notification.Status.QUEUED  # untouched — we backed off


def test_send_email_skips_an_already_SENT_row(tenant_a):
    from core.models import Notification
    from core.tasks import send_email_notification

    n = _notification(tenant_a, status=Notification.Status.SENT)
    send_email_notification(n.id)
    n.refresh_from_db()
    assert n.status == Notification.Status.SENT


@override_settings(
    DJANGO_ENV="production",
    EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
)
def test_send_email_fails_closed_on_console_backend_in_production(tenant_a):
    from core.models import Notification
    from core.tasks import send_email_notification

    n = _notification(tenant_a)
    send_email_notification(n.id)
    n.refresh_from_db()
    assert n.status == Notification.Status.FAILED
    assert "SMTP is not configured" in (n.error or "")


def test_send_email_marks_SENT_via_locmem_backend(tenant_a):
    from django.core import mail

    from core.models import Notification
    from core.tasks import send_email_notification

    mail.outbox.clear()
    n = _notification(tenant_a, recipient="ok@x.test")
    send_email_notification(n.id)
    n.refresh_from_db()
    assert n.status == Notification.Status.SENT
    assert mail.outbox and mail.outbox[-1].to == ["ok@x.test"]


# --- prune tasks -----------------------------------------------------------

def test_prune_help_events_task_drops_only_old_rows(tenant_a):
    from core.models import HelpEvent
    from core.tasks import prune_help_events_task

    old = HelpEvent.objects.create(company=tenant_a.company, name="help_open", intent_id="x")
    HelpEvent.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=400))
    HelpEvent.objects.create(company=tenant_a.company, name="help_open", intent_id="y")  # fresh

    deleted = prune_help_events_task(days=180)
    assert deleted == 1
    assert HelpEvent.objects.filter(company=tenant_a.company).count() == 1


def test_prune_idempotency_records_task_keeps_recent_and_inflight(tenant_a):
    from core.idempotency import IN_FLIGHT_STATUS
    from core.models import IdempotencyRecord
    from core.tasks import prune_idempotency_records_task

    now = timezone.now()

    def _rec(scope, key, status, age):
        r = IdempotencyRecord.objects.create(
            company=tenant_a.company, scope=scope, key=key, status_code=status, body={},
        )
        IdempotencyRecord.objects.filter(pk=r.pk).update(created_at=now - age)
        return r

    old_done = _rec("s", "k-old-done", 200, timedelta(days=40))
    recent_done = _rec("s", "k-recent-done", 200, timedelta(days=5))
    stale_inflight = _rec("s", "k-stale-inflight", IN_FLIGHT_STATUS, timedelta(hours=30))
    fresh_inflight = _rec("s", "k-fresh-inflight", IN_FLIGHT_STATUS, timedelta(minutes=10))

    prune_idempotency_records_task(days=30)

    remaining = set(IdempotencyRecord.objects.values_list("key", flat=True))
    assert old_done.key not in remaining
    assert stale_inflight.key not in remaining
    assert recent_done.key in remaining
    assert fresh_inflight.key in remaining
