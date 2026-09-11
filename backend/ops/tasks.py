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

Your job is synthesis, not re-listing: spot patterns a mechanical count misses \
(e.g. "every Payments screen is uncovered and Payments touches money — that's a \
bigger risk than the raw count suggests"), prioritize, and draft concrete, \
actionable recommendations. Do not invent routes or specs not present in the input.

Respond with ONLY a JSON array (no prose, no markdown fences) of objects shaped \
exactly like:
[{"area": "short area name", "gap": "one-sentence description of the gap", \
"severity": "low|medium|high", "recommendation": "one concrete next step", \
"related_qos_ids": ["QOS-0010"]}]

Return at most 15 items, ordered most-severe first."""

# BUG-306-style: cap total task runtime so a hung/slow LLM provider can't
# wedge a worker forever.
_TIME_LIMIT = 300
_SOFT_TIME_LIMIT = 270


@shared_task(time_limit=_TIME_LIMIT, soft_time_limit=_SOFT_TIME_LIMIT)
def run_coverage_audit_task(run_id: int):
    from celery.exceptions import SoftTimeLimitExceeded

    from core.exceptions import BusinessRuleError
    from core.services.llm import chat_with_tools
    from ops.coverage_scan import scan
    from ops.models import CoverageAuditRun

    try:
        run = CoverageAuditRun.objects.get(pk=run_id)
    except CoverageAuditRun.DoesNotExist:
        return
    if run.status != CoverageAuditRun.Status.PENDING:
        return

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
