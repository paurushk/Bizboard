"""Company / tenant maintenance Celery tasks."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def run_scheduled_backups_task():
    """SET-08: weekly encrypted backup for every company that switched it on; one failure never stops the rest."""
    from accounts.models import Company
    from accounts.scheduled_backup import run_scheduled_backup

    done = failed = 0
    for company in Company.objects.filter(scheduled_backup_enabled=True, is_sandbox=False).iterator():
        if run_scheduled_backup(company) is None:
            failed += 1
        else:
            done += 1
    logger.info("run_scheduled_backups_task: %s taken, %s failed", done, failed)
    return {"taken": done, "failed": failed}


@shared_task
def run_settings_alerts_task():
    """SET-23: licence expiry, quiet gateway and plan-limit alerts for every live company."""
    from accounts.models import Company
    from accounts.settings_alerts import run_settings_alerts

    total = 0
    for company in Company.objects.filter(is_sandbox=False).iterator():
        total += run_settings_alerts(company)
    logger.info("run_settings_alerts_task sent %s alerts", total)
    return total


@shared_task
def sweep_expired_sandboxes_task():
    """R-014: daily wipe+delete of sandbox companies past sandbox_expires_at."""
    from accounts.tenant_backup import sweep_expired_sandboxes

    deleted = sweep_expired_sandboxes()
    logger.info("sweep_expired_sandboxes_task removed %s expired sandbox companies", deleted)
    return deleted
