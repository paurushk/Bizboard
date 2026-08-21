import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def send_email_notification(self, notification_id):
    """BB-000530: Celery retries must not duplicate sends — SENT rows are skipped."""
    from core.models import Notification

    notification = Notification.objects.get(pk=notification_id)
    if notification.status == Notification.Status.SENT:
        logger.info("Email notification %s already sent; skipping retry", notification_id)
        return
    backend = (settings.EMAIL_BACKEND or "").lower()
    env = (getattr(settings, "DJANGO_ENV", "") or "").lower()
    # Fail closed: never pretend email was sent via console in prod/staging.
    if env in ("production", "staging") and "console" in backend:
        notification.status = Notification.Status.FAILED
        notification.error = "SMTP is not configured (console email backend forbidden)."
        notification.save(update_fields=["status", "error"])
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
        notification.status = Notification.Status.SENT
        notification.error = ""
        notification.save(update_fields=["status", "error"])
    except Exception as exc:  # pragma: no cover - depends on SMTP env
        notification.status = Notification.Status.FAILED
        notification.error = str(exc)
        notification.save(update_fields=["status", "error"])
        logger.exception("Email notification %s failed", notification_id)
        raise


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
