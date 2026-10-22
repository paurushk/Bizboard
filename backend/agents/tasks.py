"""Celery tasks. Every per-company task takes ``company_id`` as a kwarg so the worker can set the RLS
context before touching tenant rows (config/celery.py)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger("agents")

_LOCK_TTL = 15 * 60


def _flagged_company_ids():
    from accounts.models import Company

    return list(Company.objects.filter(feature_flags__has_key="ENABLE_AGENTS").values_list("pk", flat=True))


@shared_task(name="agents.tasks.run_agent_async")
def run_agent_async(run_id, company_id=None):
    from .runner import execute_run

    run = execute_run(run_id)
    return {"ok": run is not None, "run_id": run_id, "status": getattr(run, "status", None)}


@shared_task(name="agents.tasks.dispatch_scheduled_agents")
def dispatch_scheduled_agents(now_iso=None):
    """One beat entry for every scheduled agent: fan out per company for each spec that is due now.

    Runs every 15 minutes (IST). A spec's ``schedule`` {"hour", "minute"} is due when it falls inside
    the window [now - 15 min, now).
    """
    from .spec import AGENTS

    now = timezone.localtime(timezone.now()) if now_iso is None else datetime.fromisoformat(now_iso)
    window_start = now - timedelta(minutes=15)
    queued = 0
    for spec in AGENTS.values():
        sched = spec.schedule
        if not sched:
            continue
        due = now.replace(hour=int(sched.get("hour", 0)), minute=int(sched.get("minute", 0)), second=0, microsecond=0)
        if not (window_start < due <= now):
            continue
        for cid in _flagged_company_ids():
            run_scheduled_agent_company.delay(spec.kind, company_id=cid)
            queued += 1
    return {"ok": True, "queued": queued}


@shared_task(name="agents.tasks.run_scheduled_agent_company")
def run_scheduled_agent_company(agent_kind, company_id=None):
    from accounts.models import Company

    from . import policy, runner, services
    from .enums import Trigger
    from .spec import AGENTS

    spec = AGENTS.get(agent_kind)
    company = Company.objects.filter(pk=company_id).first()
    if spec is None or company is None or not policy.agent_enabled(company, spec):
        return {"ok": False, "skipped": "disabled"}
    lock_key = f"agents:sweep:{agent_kind}:{company_id}"
    if not cache.add(lock_key, 1, _LOCK_TTL):
        return {"ok": False, "skipped": "locked"}
    try:
        today = timezone.localdate().isoformat()
        run = services.create_run(company=company, agent_kind=agent_kind, trigger=Trigger.SCHEDULE, trigger_ref=f"sweep:{today}")
        run = runner.execute_run(run.pk)
        return {"ok": True, "run_id": run.pk if run else None, "status": getattr(run, "status", None)}
    finally:
        cache.delete(lock_key)


def _company_ids_with_pending(kind=None):
    """Company ids that have PENDING proposals. Read under the RLS bypass: a beat task has no
    tenant, and FORCE RLS would otherwise hide every row (SR0-06)."""
    from core.rls import rls_bypass

    from .enums import ProposalStatus
    from .models import AgentProposal

    with rls_bypass():
        qs = AgentProposal.objects.filter(status=ProposalStatus.PENDING)
        if kind is not None:
            qs = qs.filter(kind=kind)
        return sorted(set(qs.values_list("company_id", flat=True)))


@shared_task(name="agents.tasks.expire_proposals")
def expire_proposals():
    """Orchestrator: one task per company with pending proposals (the worker sets RLS from company_id)."""
    ids = _company_ids_with_pending()
    for company_id in ids:
        expire_proposals_company.delay(company_id=company_id)
    return {"ok": True, "companies": len(ids)}


@shared_task(name="agents.tasks.expire_proposals_company")
def expire_proposals_company(company_id=None):
    from accounts.models import Company

    from .services import expire_due

    company = Company.objects.filter(pk=company_id).first()
    if company is None:
        return {"ok": False, "expired": 0}
    return {"ok": True, "expired": expire_due(company=company)}


@shared_task(name="agents.tasks.cancel_resolved")
def cancel_resolved():
    """Orchestrator: cancel PENDING drafts whose condition has cleared, one task per company."""
    from .spec import AGENTS

    ids: set = set()
    for spec in AGENTS.values():
        if spec.still_open is None:
            continue
        for kind in (k.kind for k in spec.proposal_kinds):
            ids.update(_company_ids_with_pending(kind))
    for company_id in sorted(ids):
        cancel_resolved_company.delay(company_id=company_id)
    return {"ok": True, "companies": len(ids)}


@shared_task(name="agents.tasks.cancel_resolved_company")
def cancel_resolved_company(company_id=None):
    """Cancel one company's PENDING drafts whose condition has cleared. A spec opts in with ``still_open``."""
    from accounts.models import Company

    from .enums import ProposalStatus
    from .models import AgentProposal
    from .services import cancel_live_for_keys
    from .spec import AGENTS

    company = Company.objects.filter(pk=company_id).first()
    if company is None:
        return {"ok": False, "cancelled": 0}
    cancelled = 0
    for spec in AGENTS.values():
        if spec.still_open is None:
            continue
        for kind in (k.kind for k in spec.proposal_kinds):
            keys = list(
                AgentProposal.objects.filter(company=company, kind=kind, status=ProposalStatus.PENDING)
                .values_list("dedupe_key", flat=True)
            )
            if not keys:
                continue
            open_keys = set(spec.still_open(company, keys))
            gone = [k for k in keys if k not in open_keys]
            if gone:
                cancelled += cancel_live_for_keys(company, kind, gone)
    return {"ok": True, "cancelled": cancelled}


@shared_task(name="agents.tasks.purge_steps")
def purge_steps():
    """Delete step records past retention, company by company so RLS never needs a bypass."""
    from accounts.models import Company

    total = 0
    for pk in Company.objects.values_list("pk", flat=True):
        purge_steps_company.delay(company_id=pk)
        total += 1
    return {"ok": True, "companies": total}


@shared_task(name="agents.tasks.purge_steps_company")
def purge_steps_company(company_id=None):
    from django.conf import settings

    from .models import AgentStep

    cutoff = timezone.now() - timedelta(days=settings.AGENTS["STEP_RETENTION_DAYS"])
    deleted, _ = AgentStep.objects.filter(company_id=company_id, created_at__lt=cutoff).delete()
    return {"ok": True, "deleted": deleted}
