"""WP-E1 / DIM6-09: the nightly books check, one company at a time.

``nightly_invariants_task`` (core/tasks.py) is a thin orchestrator: it queues one
``sweep_company_task`` per company with ``company_id`` so the worker sets that
company's RLS context (config/celery.py). Each company's result is one
``TenantSweepResult`` row, shown to ops in Django admin.

A company is skipped only when nothing could have changed its books since its last
clean check. Every company still gets a full check at least weekly: on its rotation
day (``company_id % 7 == weekday``) and whenever its last clean check is older than
``FULL_SWEEP_MAX_AGE``. The change signal looks at ledger and stock rows as well as
audit events, so a write path that forgot its audit event cannot hide a company.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("core.tasks")

FULL_SWEEP_MAX_AGE = timedelta(days=7)
RESULT_RETENTION = timedelta(days=90)


def new_run_id() -> str:
    return str(uuid.uuid4())


def all_company_ids() -> list[int]:
    from accounts.models import Company
    from core.rls import rls_bypass

    with rls_bypass():
        return list(Company.objects.order_by("pk").values_list("pk", flat=True))


def is_rotation_day(company_id: int, now) -> bool:
    return company_id % 7 == now.weekday()


def changed_since(company, since) -> bool:
    """True when any audit, ledger or stock row for ``company`` is newer than ``since``."""
    from accounting.models import JournalEntry
    from core.models import AuditEvent
    from inventory.models import StockMovement

    return (
        AuditEvent.objects.filter(company=company, created_at__gt=since).exists()
        or JournalEntry.objects.filter(company=company, updated_at__gt=since).exists()
        or StockMovement.objects.filter(company=company, created_at__gt=since).exists()
    )


def needs_full_sweep(company, last_clean, now) -> bool:
    if last_clean is None:
        return True
    if now - last_clean.started_at > FULL_SWEEP_MAX_AGE:
        return True
    return is_rotation_day(company.pk, now)


def _quarantine_and_notify(company, failures: dict) -> None:
    from core.rls import rls_bypass
    from core.tasks import _notify_invariant_failure
    from planwave.services import open_quarantine

    keys = sorted(failures.keys())
    logger.error("nightly_invariants company=%s keys=%s", company.pk, keys)
    try:
        with rls_bypass():
            open_quarantine(company, failures)
            _notify_invariant_failure(company, keys)
    except Exception:  # noqa: BLE001 - the result row is still written
        logger.exception("nightly_invariants could not quarantine company=%s", company.pk)
    ops = getattr(settings, "OPS_ALERT_EMAIL", "") or ""
    if ops:
        logger.error("books quarantine ops_mailbox=%s company=%s", ops, company.pk)


def sweep_company(company_id: int, run_id: str, *, force_full: bool = False, now=None):
    """Check one company's books and record the result. Never raises for a check failure."""
    from accounts.models import Company
    from core.invariants import run_invariants
    from core.models import TenantSweepResult
    from core.rls import rls_bypass

    now = now or timezone.now()
    started = time.monotonic()
    with rls_bypass():
        company = Company.objects.filter(pk=company_id).first()
        if company is None:
            return None
        last_clean = (
            TenantSweepResult.objects.filter(company=company, status=TenantSweepResult.Status.CLEAN)
            .order_by("-started_at")
            .first()
        )
        full = force_full or needs_full_sweep(company, last_clean, now)
        if not full and not changed_since(company, last_clean.started_at):
            return _record(company, run_id, TenantSweepResult.Status.SKIPPED, now, started, full=False)
        try:
            failures = run_invariants(company)
        except Exception as exc:  # noqa: BLE001 - one company's crash must not hide the others
            logger.exception("nightly_invariants crashed company=%s", company_id)
            return _record(
                company, run_id, TenantSweepResult.Status.ERROR, now, started, full=full,
                error=f"{type(exc).__name__}: {exc}"[:500],
            )
    if failures:
        _quarantine_and_notify(company, failures)
        with rls_bypass():
            return _record(
                company, run_id, TenantSweepResult.Status.FAILED, now, started, full=full,
                keys=sorted(failures.keys()),
            )
    with rls_bypass():
        return _record(company, run_id, TenantSweepResult.Status.CLEAN, now, started, full=full)


def _record(company, run_id, status, now, started, *, full, keys=None, error=""):
    from core.models import TenantSweepResult

    return TenantSweepResult.objects.create(
        company=company,
        run_id=run_id,
        status=status,
        full_sweep=full,
        failing_keys=keys or [],
        error=error,
        started_at=now,
        finished_at=timezone.now(),
        duration_ms=int((time.monotonic() - started) * 1000),
    )


def prune_old_results(now=None) -> int:
    from core.models import TenantSweepResult
    from core.rls import rls_bypass

    cutoff = (now or timezone.now()) - RESULT_RETENTION
    with rls_bypass():
        deleted, _ = TenantSweepResult.objects.filter(started_at__lt=cutoff).delete()
    return deleted


def latest_status_by_company() -> dict[int, str]:
    """Each company's most recent non-SKIPPED status (CLEAN / FAILED / ERROR)."""
    from core.models import TenantSweepResult
    from core.rls import rls_bypass

    out: dict[int, str] = {}
    with rls_bypass():
        rows = (
            TenantSweepResult.objects.exclude(status=TenantSweepResult.Status.SKIPPED)
            .order_by("company_id", "-started_at", "-id")
            .values_list("company_id", "status")
        )
        for company_id, status in rows:
            out.setdefault(company_id, status)
    return out


def failing_company_count() -> int:
    """Companies whose latest books check failed or crashed (the ops alert gauge)."""
    return sum(1 for s in latest_status_by_company().values() if s in ("FAILED", "ERROR"))
