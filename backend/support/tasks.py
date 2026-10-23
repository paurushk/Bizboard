"""Support beat jobs: tenant health snapshots (WP-PO2) and owner recoveries (WP-ID1)."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def tenant_health_weekly_task():
    """WP-PO2 orchestrator: one ``tenant_health_company_task`` per company."""
    from core.rls import rls_bypass

    from .health import _real_companies

    with rls_bypass():
        ids = list(_real_companies().order_by("pk").values_list("pk", flat=True))
    for pk in ids:
        tenant_health_company_task.delay(company_id=pk)
    return {"queued": len(ids)}


@shared_task
def tenant_health_company_task(company_id=None):
    """One company's health snapshot. ``company_id`` kwarg lets the worker set RLS."""
    from .health import snapshot_company

    row = snapshot_company(company_id)
    return {"company_id": company_id, "score": row.score}


@shared_task
def complete_owner_recoveries_task():
    """WP-ID1: send the owner invite for approved recoveries whose 72-hour wait has passed.

    Visits only due recovery rows (a handful at most), not every company.
    """
    from accounts.ownership import complete_due_recoveries
    from core.rls import rls_bypass

    with rls_bypass():
        done = complete_due_recoveries()
    if done:
        logger.info("Owner recoveries completed: %s", done)
    return {"completed": done}


@shared_task
def expire_support_access_task():
    """WP-ID4: revoke support access grants that ran out or whose ticket is resolved (live rows only)."""
    from support.access import expire_due_grants

    n = expire_due_grants()
    if n:
        logger.info("Support access grants revoked: %s", n)
    return {"revoked": n}
