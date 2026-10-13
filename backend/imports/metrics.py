"""Operational signals for bill imports (UPLOAD_SALES_BILL_REVIEW 4.2).

Each event is one structured log line on `bizboard.metrics`, so any log
pipeline can count them without a schema change. `report_bill_import_stats`
summarises the same story from the database.
"""

import json
import logging

from django.utils import timezone

logger = logging.getLogger("bizboard.metrics")


def _emit(event: str, **fields) -> None:
    try:
        logger.info(json.dumps({"event": event, **fields}, default=str))
    except Exception:  # noqa: BLE001 — metrics must never break an import
        pass


def record_commit(job, all_lines, included, excluded) -> None:
    edited = len([ln for ln in included if ln.get("edited")])
    seconds = None
    if job.created_at is not None:
        seconds = round((timezone.now() - job.created_at).total_seconds(), 1)
    _emit(
        "bill_import_commit",
        company_id=job.company_id, kind=job.kind, job_id=job.pk,
        lines_total=len(all_lines), lines_included=len(included),
        lines_excluded=len(excluded), lines_edited=edited,
        seconds_to_commit=seconds,
    )


def record_rejection(job, exc) -> None:
    extra = getattr(exc, "extra", {}) or {}
    codes = sorted(
        {e.get("code") for row in extra.get("lineErrors", []) for e in row.get("errors", [])}
        | {e.get("code") for e in extra.get("headerErrors", [])}
    )
    _emit(
        "bill_import_rejected",
        company_id=job.company_id, kind=job.kind, job_id=job.pk,
        bad_lines=len(extra.get("lineErrors", [])), codes=codes,
    )


def summary(days: int = 30, company_id: int | None = None) -> list[dict]:
    """Per-direction health numbers from the database (used by the command and the admin page)."""
    from datetime import timedelta

    from core.models import AuditEvent
    from imports.models import ImportJob

    since = timezone.now() - timedelta(days=days)
    qs = ImportJob.objects.filter(kind__in=ImportJob.BILL_KINDS, created_at__gte=since)
    if company_id:
        qs = qs.filter(company_id=company_id)
    rejected_qs = AuditEvent.objects.filter(
        action="IMPORT", entity_type="ImportJob", created_at__gte=since, metadata__event="IMPORT_REJECTED",
    )
    if company_id:
        rejected_qs = rejected_qs.filter(company_id=company_id)
    rejected = rejected_qs.count()
    out = []
    for kind in ImportJob.BILL_KINDS:
        jobs = list(qs.filter(kind=kind))
        by_status: dict[str, int] = {}
        for job in jobs:
            by_status[job.status] = by_status.get(job.status, 0) + 1
        committed = [j for j in jobs if j.status == ImportJob.Status.COMMITTED]
        lines = edited = excluded = 0
        seconds = []
        for job in committed:
            rows = (job.preview or {}).get("lines") if isinstance(job.preview, dict) else []
            rows = rows or []
            lines += len(rows)
            edited += len([r for r in rows if r.get("include") and r.get("edited")])
            excluded += len([r for r in rows if not r.get("include")])
            if job.committed_at and job.created_at:
                seconds.append((job.committed_at - job.created_at).total_seconds())
        total = len(jobs)
        out.append({
            "kind": kind,
            "uploads": total,
            "by_status": by_status,
            "failure_rate": (by_status.get(ImportJob.Status.FAILED, 0) / total) if total else None,
            "committed": len(committed),
            "mean_minutes_to_draft": (sum(seconds) / len(seconds) / 60) if seconds else None,
            "edited_share": (edited / lines) if lines else None,
            "excluded_share": (excluded / lines) if lines else None,
            "rejected_commits": rejected if kind == ImportJob.Kind.SALES_BILL else None,
        })
    return out


def record_failure(job, reason: str) -> None:
    _emit(
        "bill_import_failed",
        company_id=job.company_id, kind=job.kind, job_id=job.pk, reason=str(reason)[:200],
    )
