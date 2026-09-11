from __future__ import annotations

import json
import logging

from celery import shared_task

logger = logging.getLogger("bizboard.ops")

_SYSTEM_PROMPT = """You are a QA/test-coverage analyst for an Indian ERP product \
(Bizboard). You are given a structured JSON scan of the frontend's routes, which \
e2e/Playwright specs (if any) actually exercise each route, the currently-open \
items in the engineering quality backlog (QOS ids), and the raw G-register rows \
from the testing-strategy doc.

GROUNDING RULE — the most important constraint: `route_coverage` is the ONLY \
source of truth for whether a route is tested. Its `class` field is exactly one \
of "flow" (a real dedicated spec exercises it — treat as adequately covered, \
never call it a gap), "smoke" (render-only check exists — a legitimate but \
smaller gap than "none"), or "none" (zero coverage — the real gaps). Before \
naming any area as a gap, check its routes' `class` values; if they're all \
"flow", do not report it. The g_register text and open QOS items describe \
past/qualitative state and may be stale relative to `route_coverage` — when \
they conflict, `route_coverage` wins. Do not reuse phrasing that sounds like a \
worked example; every claim must trace to a specific "none" or "smoke" route in \
the input you were actually given, and named by that field's own domain \
grouping, not a memorized pattern.

Your job is synthesis, not re-listing: spot patterns a mechanical count misses \
(a domain where every route is "none" AND it moves money deserves a higher \
severity than the raw count alone suggests), prioritize, and draft concrete, \
actionable recommendations. Do not invent routes or specs not present in the input.

Respond with ONLY a JSON array (no prose, no markdown fences) of objects shaped \
exactly like:
[{"area": "short area name", "gap": "one-sentence description naming the actual \
uncovered route(s) from route_coverage", "severity": "low|medium|high", \
"recommendation": "one concrete next step", "related_qos_ids": ["QOS-0010"]}]

Return at most 15 items, ordered most-severe first."""

# BUG-306-style: cap total task runtime so a hung/slow LLM provider can't
# wedge a worker forever.
_TIME_LIMIT = 300
_SOFT_TIME_LIMIT = 270


@shared_task(time_limit=_TIME_LIMIT, soft_time_limit=_SOFT_TIME_LIMIT)
def run_coverage_audit_task(run_id: int):
    from ops.models import CoverageAuditRun

    try:
        run = CoverageAuditRun.objects.get(pk=run_id)
    except CoverageAuditRun.DoesNotExist:
        return
    if run.status != CoverageAuditRun.Status.PENDING:
        return
    _execute_coverage_audit(run)


@shared_task(time_limit=_TIME_LIMIT, soft_time_limit=_SOFT_TIME_LIMIT)
def run_scheduled_coverage_audit():
    """Weekly, unattended counterpart to the admin-triggered run — only
    registered in CELERY_BEAT_SCHEDULE when ENABLE_SCHEDULED_COVERAGE_AUDIT
    is on (config/settings.py). `requested_by` stays null: no admin clicked
    this one.
    """
    from ops.models import CoverageAuditRun

    run = CoverageAuditRun.objects.create(status=CoverageAuditRun.Status.PENDING)
    _execute_coverage_audit(run)


def _execute_coverage_audit(run) -> None:
    from celery.exceptions import SoftTimeLimitExceeded

    from core.exceptions import BusinessRuleError
    from core.services.llm import chat_with_tools
    from ops.coverage_scan import scan
    from ops.models import CoverageAuditRun

    run_id = run.pk
    run.status = CoverageAuditRun.Status.RUNNING
    run.save(update_fields=["status", "updated_at"])

    try:
        context = scan()
        if context.get("source") == "unavailable":
            run.status = CoverageAuditRun.Status.FAILED
            run.failure_reason = context.get("note", "Repo scan unavailable.")
            run.save(update_fields=["status", "failure_reason", "updated_at"])
            return

        response = chat_with_tools(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(context)},
            ]
        )
        content = (response.get("content") or "").strip()
        # Tolerate a stray ```json fence even though the prompt asks against it.
        if content.startswith("```"):
            content = content.strip("`")
            if content.startswith("json"):
                content = content[4:]
        try:
            parsed = json.loads(content)
            if not isinstance(parsed, list):
                raise ValueError("LLM response was not a JSON array")
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Coverage audit run=%s: unparseable LLM response: %s", run_id, exc)
            parsed = [{
                "area": "parse-error",
                "gap": "The LLM response could not be parsed as the expected JSON shape.",
                "severity": "low",
                "recommendation": "Re-run; raw response logged server-side.",
                "related_qos_ids": [],
            }]
            logger.info("Coverage audit run=%s raw content: %s", run_id, content[:4000])

        run.status = CoverageAuditRun.Status.DONE
        run.result = parsed
        run.save(update_fields=["status", "result", "updated_at"])
    except BusinessRuleError as exc:
        run.status = CoverageAuditRun.Status.FAILED
        run.failure_reason = str(getattr(exc, "detail", exc))
        run.save(update_fields=["status", "failure_reason", "updated_at"])
    except SoftTimeLimitExceeded:
        run.status = CoverageAuditRun.Status.FAILED
        run.failure_reason = "Coverage audit timed out — please retry."
        run.save(update_fields=["status", "failure_reason", "updated_at"])
    except Exception as exc:  # noqa: BLE001 — surface to failure_reason, never crash the worker
        run.status = CoverageAuditRun.Status.FAILED
        run.failure_reason = str(exc)
        run.save(update_fields=["status", "failure_reason", "updated_at"])
