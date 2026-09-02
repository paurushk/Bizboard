import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def send_email_notification(self, notification_id, company_id=None):
    """BB-000530: Celery retries must not duplicate sends — SENT rows are skipped.

    CORE-13: dedup with a short cache lock (Redis SETNX) instead of holding a
    ``select_for_update`` row lock + DB connection open across the whole SMTP
    round trip.
    """
    from django.core.cache import cache

    from core.models import Notification

    lock_key = f"bizboard:email_send:{notification_id}"
    if not cache.add(lock_key, "1", timeout=180):
        logger.info("Email notification %s send already in flight; skipping", notification_id)
        return
    try:
        notification = Notification.objects.get(pk=notification_id)
        if notification.status == Notification.Status.SENT:
            logger.info("Email notification %s already sent; skipping retry", notification_id)
            return
        backend = (settings.EMAIL_BACKEND or "").lower()
        env = (getattr(settings, "DJANGO_ENV", "") or "").lower()
        # Fail closed: never pretend email was sent via console in prod/staging.
        if env in ("production", "staging") and "console" in backend:
            Notification.objects.filter(pk=notification_id).update(
                status=Notification.Status.FAILED,
                error="SMTP is not configured (console email backend forbidden).",
            )
            logger.error("Email notification %s blocked: console backend in %s", notification_id, env)
            return
        try:
            send_mail(
                subject=notification.subject or "Bizboard",
                message=notification.body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[notification.recipient],
                fail_silently=False,
            )
            Notification.objects.filter(pk=notification_id).update(
                status=Notification.Status.SENT, error=""
            )
        except Exception as exc:  # pragma: no cover - depends on SMTP env
            Notification.objects.filter(pk=notification_id).update(
                status=Notification.Status.FAILED, error=str(exc)
            )
            logger.exception("Email notification %s failed", notification_id)
            raise
    finally:
        cache.delete(lock_key)


BEAT_HEARTBEAT_KEY = "bizboard:celery_beat_heartbeat"


@shared_task
def celery_beat_heartbeat():
    """BB-000359 / BB-000456: unix-epoch heartbeat for compose float() + HealthView.

    Writes the same epoch string to Django cache and bare Redis key
    ``bizboard:celery_beat_heartbeat`` (compose.prod healthcheck reads raw Redis).
    """
    import time

    from django.core.cache import cache

    epoch = str(time.time())
    cache.set(BEAT_HEARTBEAT_KEY, epoch, timeout=900)
    redis_url = (getattr(settings, "REDIS_URL", None) or "").strip()
    if redis_url:
        try:
            import redis

            client = redis.from_url(redis_url)
            client.set(BEAT_HEARTBEAT_KEY, epoch, ex=900)
        except Exception:  # noqa: BLE001 — cache write already succeeded
            logger.exception("Failed to write bare Redis beat heartbeat key")


@shared_task
def prune_help_events_task(days=180, company_id=None):
    """Weekly retention: drop HelpEvent rows older than ``days`` (default 180).

    ``company_id`` is accepted so Celery RLS prerun can set a GUC; prune then
    raises ``app.help_staff_all`` so FORCE RLS does not hide other tenants.
    """
    from datetime import timedelta

    from django.utils import timezone

    from core.models import HelpEvent
    from core.rls import rls_bypass

    _ = company_id
    # Cross-tenant retention sweep — RLS bypass (SYS-01).
    with rls_bypass():
        cutoff = timezone.now() - timedelta(days=max(1, int(days)))
        deleted, _counts = HelpEvent.objects.filter(created_at__lt=cutoff).delete()
        logger.info("prune_help_events_task deleted %s rows older than %s days", deleted, days)
        return deleted


@shared_task
def prune_idempotency_records_task(days=30):
    """CORE-05: `IdempotencyRecord` rows are durable with no natural expiry — an
    unbounded table otherwise. A client can only replay a key for a short window
    after the original request; a *completed* row older than ``days`` is safe to
    drop. In-flight placeholders older than the hard-stale window are also
    reclaimed (a crash between the request's commit and `store_record` otherwise
    bricks that key forever — CORE-04).
    """
    from datetime import timedelta

    from django.utils import timezone

    from core.idempotency import IN_FLIGHT_STATUS
    from core.models import IdempotencyRecord
    from core.rls import rls_bypass

    now = timezone.now()
    completed_cutoff = now - timedelta(days=max(1, int(days)))
    stale_inflight_cutoff = now - timedelta(hours=24)

    with rls_bypass():  # cross-tenant sweep (SYS-01)
        done_deleted, _ = (
            IdempotencyRecord.objects.filter(created_at__lt=completed_cutoff)
            .exclude(status_code=IN_FLIGHT_STATUS)
            .delete()
        )
        inflight_deleted, _ = IdempotencyRecord.objects.filter(
            status_code=IN_FLIGHT_STATUS, created_at__lt=stale_inflight_cutoff
        ).delete()
    logger.info(
        "prune_idempotency_records_task: %s completed + %s stale in-flight rows removed",
        done_deleted,
        inflight_deleted,
    )
    return done_deleted + inflight_deleted
