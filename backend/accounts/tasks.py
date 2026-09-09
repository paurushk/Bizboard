"""Company / tenant maintenance Celery tasks."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def sweep_expired_sandboxes_task():
    """R-014: daily wipe+delete of sandbox companies past sandbox_expires_at."""
    from accounts.tenant_backup import sweep_expired_sandboxes

    deleted = sweep_expired_sandboxes()
    logger.info("sweep_expired_sandboxes_task removed %s expired sandbox companies", deleted)
    return deleted
