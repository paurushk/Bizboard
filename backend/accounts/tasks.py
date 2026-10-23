"""Company / tenant maintenance Celery tasks."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


def _live_company_ids(**filters):
    """Company ids for a per-company fan-out. Read under the RLS bypass: a beat task has no tenant."""
    from accounts.models import Company
    from core.rls import rls_bypass

    with rls_bypass():
        return list(Company.objects.filter(is_sandbox=False, **filters).order_by("pk").values_list("pk", flat=True))


@shared_task
def run_scheduled_backups_task():
    """SET-08 orchestrator: one backup task per company that switched it on (WP-E1).

    Each task runs under that company's RLS context, so one failure never stops the rest
    and the backup reads the company's rows (an unscoped read sees none under FORCE RLS).
    """
    ids = _live_company_ids(scheduled_backup_enabled=True)
    for pk in ids:
        run_scheduled_backup_company_task.delay(company_id=pk)
    logger.info("run_scheduled_backups_task queued %s companies", len(ids))
    return {"queued": len(ids)}


@shared_task(queue="media_heavy")
def run_scheduled_backup_company_task(company_id=None):
    from accounts.models import Company
    from accounts.scheduled_backup import run_scheduled_backup

    company = Company.objects.filter(pk=company_id).first()
    if company is None:
        return {"company_id": company_id, "ok": False}
    return {"company_id": company_id, "ok": run_scheduled_backup(company) is not None}


@shared_task
def run_settings_alerts_task():
    """SET-23 orchestrator: licence expiry, quiet gateway and plan-limit alerts, one task per live company."""
    ids = _live_company_ids()
    for pk in ids:
        run_settings_alerts_company_task.delay(company_id=pk)
    logger.info("run_settings_alerts_task queued %s companies", len(ids))
    return {"queued": len(ids)}


@shared_task
def run_settings_alerts_company_task(company_id=None):
    from accounts.models import Company
    from accounts.settings_alerts import run_settings_alerts

    company = Company.objects.filter(pk=company_id).first()
    return run_settings_alerts(company) if company is not None else 0


@shared_task
def sweep_expired_sandboxes_task():
    """R-014: daily wipe+delete of sandbox companies past sandbox_expires_at."""
    from accounts.tenant_backup import sweep_expired_sandboxes

    deleted = sweep_expired_sandboxes()
    logger.info("sweep_expired_sandboxes_task removed %s expired sandbox companies", deleted)
    return deleted


@shared_task(queue="reports")
def build_readable_export_task(export_id: int, company_id: int | None = None):
    """WP-DL1: build one readable (CSV + PDF) export off the request path."""
    from accounts.readable_export import run_export

    run_export(export_id)


@shared_task
def purge_readable_exports_task():
    """WP-DL1: remove readable export ZIPs whose download link ran out."""
    from accounts.readable_export import purge_expired

    return {"purged": purge_expired()}


@shared_task
def new_device_email_task(user_id=None, label="", prefix=""):
    """WP-ID3: the "new sign-in" security email, off the sign-in request."""
    from .user_sessions import _new_device_email

    _new_device_email(None, user_id, label, prefix)
    return {"user_id": user_id}
