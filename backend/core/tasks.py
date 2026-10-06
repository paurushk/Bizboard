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
        from core.idempotency import _is_money_idempotency_scope

        stale = IdempotencyRecord.objects.filter(status_code=IN_FLIGHT_STATUS, created_at__lt=stale_inflight_cutoff)
        # A money key left in flight may belong to a request whose money already posted (the worker
        # died before the answer was stored). Deleting it would let a late retry post that money a
        # second time, so it is reported for a person to look at instead.
        money_ids = [r.pk for r in stale.only("pk", "scope") if _is_money_idempotency_scope(r.scope)]
        if money_ids:
            logger.error(
                "prune_idempotency_records_task: %s stale in-flight MONEY key(s) kept for review: %s",
                len(money_ids), money_ids[:20],
            )
        inflight_deleted, _ = stale.exclude(pk__in=money_ids).delete()
    logger.info(
        "prune_idempotency_records_task: %s completed + %s stale in-flight rows removed",
        done_deleted,
        inflight_deleted,
    )
    return done_deleted + inflight_deleted


def _notify_invariant_failure(company, keys) -> None:
    from accounts.models import CompanyUser
    from core.models import Notification
    from core.services.notifications import NotificationService

    owners = CompanyUser.objects.filter(
        company=company,
        is_active=True,
        role__in=(CompanyUser.Role.OWNER, CompanyUser.Role.ACCOUNTANT),
    ).select_related("user")
    body = "Books check failed: " + ", ".join(keys)
    for membership in owners:
        try:
            NotificationService.send(
                company=company,
                channel=Notification.Channel.IN_APP,
                recipient=membership.user.email or str(membership.user_id),
                subject="Books check failed",
                body=body,
                user=membership.user,
            )
        except Exception:
            logger.exception("invariant notify failed company=%s", company.pk)


@shared_task
def nightly_invariants_task():
    """5.6 — recon report: sweep every company; log failures, do not retry-storm."""
    from accounts.models import Company
    from core.invariants import run_invariants
    from core.rls import rls_bypass

    failed = 0
    checked = 0
    with rls_bypass():
        company_ids = list(Company.objects.values_list("id", flat=True))
    for pk in company_ids:
        with rls_bypass():
            company = Company.objects.filter(pk=pk).first()
            if company is None:
                continue
            checked += 1
            failures = run_invariants(company)
        if failures:
            failed += 1
            logger.error(
                "nightly_invariants company=%s keys=%s",
                pk,
                sorted(failures.keys()),
            )
            from planwave.services import open_quarantine

            # One company's write failure must not stop the sweep, and the insert needs the
            # RLS bypass (the policy would otherwise reject it with no tenant set).
            try:
                with rls_bypass():
                    open_quarantine(company, failures)
                    _notify_invariant_failure(company, sorted(failures.keys()))
            except Exception:  # noqa: BLE001 - keep checking the other companies
                logger.exception("nightly_invariants could not quarantine company=%s", pk)
            ops = getattr(settings, "OPS_ALERT_EMAIL", "") or ""
            if ops:
                logger.error("books quarantine ops_mailbox=%s company=%s", ops, pk)
    from integrations.shopify import notify_shopify_gaps

    with rls_bypass():
        notify_shopify_gaps()
    from django.db import connection

    rls_on = bool(getattr(settings, "POSTGRES_RLS_ENABLED", False))
    if connection.vendor == "postgresql" and not rls_on and getattr(settings, "DJANGO_ENV", "") == "production":
        logger.error(
            "Postgres RLS is off in production. Tenant isolation is application company_id only."
        )
    return {"checked": checked, "failed": failed, "rls_enabled": rls_on}


SEAL_HEARTBEAT_KEY = "audit_seal_last_ok"
# A night is missed when the previous success is older than this.
SEAL_GAP = 26 * 60 * 60


def seal_gap_seconds(last_ok, now) -> float | None:
    """Seconds since the last successful seal, or None when there is no prior run."""
    if last_ok is None:
        return None
    return (now - last_ok).total_seconds()


def alert_missed_seal(*, company, hours_late: float) -> None:
    """Log and notify the Owner. Same in-app channel as a failed books check."""
    from accounts.models import CompanyUser
    from core.models import Notification
    from core.services.notifications import NotificationService

    logger.error("audit seal missed company=%s hours_late=%.1f", getattr(company, "pk", None), hours_late)
    owners = CompanyUser.objects.filter(
        company=company, is_active=True, role=CompanyUser.Role.OWNER,
    ).select_related("user")
    body = "The nightly audit seal did not run."
    for membership in owners:
        try:
            NotificationService.send(
                company=company,
                channel=Notification.Channel.IN_APP,
                recipient=membership.user.email or str(membership.user_id),
                subject="Audit seal missed",
                body=body,
                user=membership.user,
            )
        except Exception:
            logger.exception("seal miss notify failed company=%s", getattr(company, "pk", None))


@shared_task
def seal_audit_chain_task():
    """F-SEC-03 — seal new audit events into the hash chain, then verify it.

    A verify failure is logged at ERROR (Sentry picks it up) and returned; it is not
    retried, because tampering does not heal on retry. A gap longer than 26 hours
    since the previous success alerts each company owner.
    """
    from django.core.cache import cache
    from django.utils import timezone

    from accounts.models import Company

    now = timezone.now()
    last_ok = cache.get(SEAL_HEARTBEAT_KEY)
    gap = seal_gap_seconds(last_ok, now)
    if gap is not None and gap > SEAL_GAP:
        hours = gap / 3600
        from core.rls import rls_bypass as _bypass

        # Notification rows are row-level secured: with no tenant set the insert is refused and
        # the alert would be swallowed by the per-owner except below.
        with _bypass():
            for company in Company.objects.all().iterator():
                alert_missed_seal(company=company, hours_late=hours)
    from core.models import AuditEvent
    from core.rls import rls_bypass
    from core.services import audit_chain

    sealed = 0
    with rls_bypass():
        ids = set(
            AuditEvent.objects.filter(sealed_at__isnull=True).values_list("company_id", flat=True).distinct()
        )
        for cid in sorted(ids, key=lambda x: (x is None, x or 0)):
            sealed += audit_chain.seal(cid)
        result = audit_chain.verify(all_companies=True)
    if not result.ok:
        logger.error("audit_chain_verify FAILED problems=%s sample=%s", len(result.problems), result.problems[:5])
    else:
        cache.set(SEAL_HEARTBEAT_KEY, now, timeout=14 * 24 * 60 * 60)
    return {"sealed": sealed, "checked": result.checked, "problems": len(result.problems)}

