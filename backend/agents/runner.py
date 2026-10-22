"""Bounded agent runner (plan 3.6).

* Not atomic: no DB transaction or row lock is held across a gateway call. Step and usage writes are
  short autocommit writes made after each call returns.
* Deterministic code owns every number. The model chooses tools, parses unstructured text and words
  drafts; a draft that fails ``spec.validate`` (for example it invents a number) falls back to the
  rules-only template for that run.
* Rules-only mode (no consent, no budget, provider down, or the agent chose it) never calls a model.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from typing import Any

from django.conf import settings
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.services import llm_gateway
from core.services.llm_gateway import LlmProviderError

from . import error_codes as E
from . import policy, pricing, redaction, registry, services, untrusted
from .enums import RunStatus, StepKind
from .models import AgentRun, AgentStep
from .prompts import load_prompt
from .spec import AgentSpec, get_agent

logger = logging.getLogger("agents")

_VOLATILE_KEYS = {"as_of", "generated_at", "created_at", "updated_at", "now", "today"}
_MAX_TOOL_RESULT_CHARS = 12000
_MAX_SUMMARY_BYTES = 8192
_PROVIDER_RETRIES = 2


class _RunAbort(Exception):
    def __init__(self, status: str, code: str):
        super().__init__(code)
        self.status, self.code = status, code


def canonical_digest(facts: Any) -> str:
    """sha256 over canonical JSON; volatile timestamps are dropped so fixtures survive date changes."""

    def clean(v):
        if isinstance(v, dict):
            return {k: clean(x) for k, x in sorted(v.items()) if k not in _VOLATILE_KEYS}
        if isinstance(v, (list, tuple)):
            return [clean(x) for x in v]
        return v

    blob = json.dumps(clean(facts), sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _company_user_for(run: AgentRun):
    if run.requested_by_id is None:
        return None
    from accounts.models import CompanyUser

    return CompanyUser.objects.filter(company=run.company, user_id=run.requested_by_id, is_active=True).first()


def _record_step(run, seq, kind, *, tool_name="", args=None, result=None, duration_ms=0, tokens_in=0, tokens_out=0):
    summary = json.dumps(redaction.redact(result if result is not None else {}), default=str)
    if len(summary.encode("utf-8")) > _MAX_SUMMARY_BYTES:
        summary_obj: Any = {"truncated": True, "preview": summary[:2000]}
    else:
        summary_obj = json.loads(summary)
    AgentStep.objects.create(
        company=run.company, run=run, seq=seq, kind=kind, tool_name=tool_name[:64],
        args=redaction.redact(args or {}), result_summary=summary_obj if isinstance(summary_obj, dict) else {"value": summary_obj},
        duration_ms=int(duration_ms), tokens_in=tokens_in, tokens_out=tokens_out,
    )


def _record_usage(run: AgentRun, spec: AgentSpec, result) -> None:
    from insights.models import AiUsageLedger

    cost, _priced = pricing.estimate_cost(result.model, result.tokens_in, result.tokens_out)
    AiUsageLedger.objects.create(
        company=run.company, feature=AiUsageLedger.Feature.AGENT, agent_kind=(spec.usage_feature_kind or spec.kind)[:48],
        tokens_in=result.tokens_in, tokens_out=result.tokens_out, model_name=(result.model or "")[:64],
        prompt_version=run.prompt_version[:32], cost_estimate=cost,
    )


def _chat_with_retry(messages, tools, *, max_tokens, timeout, meta, deadline):
    attempt = 0
    while True:
        try:
            return llm_gateway.chat(messages=messages, tools=tools, max_tokens=max_tokens, timeout=timeout, meta=meta)
        except LlmProviderError as exc:
            attempt += 1
            if not exc.transient or attempt > _PROVIDER_RETRIES or time.monotonic() >= deadline:
                raise _RunAbort(RunStatus.FAILED, E.AGT_E_PROVIDER) from exc
            time.sleep(min(0.05 * attempt + random.random() * 0.05, 1.0))  # noqa: S311 - retry jitter, not security


def _llm_drafts(run: AgentRun, spec: AgentSpec, tctx: registry.ToolContext, context: dict, deadline: float):
    """The tool loop. Returns (drafts, final_text)."""
    cfg = settings.AGENTS
    max_steps = spec.limit("max_steps", cfg["MAX_STEPS"])
    max_calls = cfg["MAX_TOOL_CALLS_PER_STEP"]
    token_cap = spec.limit("per_run_token_cap", cfg["PER_RUN_TOKEN_CAP"])
    system_text, version = load_prompt(spec.package, "system")
    run.prompt_version = version
    nonce = untrusted.new_nonce()
    user_parts = [json.dumps(redaction.redact(context.get("facts", {})), default=str)]
    flagged = False
    for name, raw in (context.get("untrusted") or {}).items():
        wrapped, _n, hit = untrusted.wrap(redaction.scrub_text(raw), nonce)
        flagged = flagged or hit
        user_parts.append(f"{name}:\n{wrapped}")
    if flagged:
        context["injection_suspected"] = True
    messages: list[dict] = [
        {"role": "system", "content": f"{system_text}\n\n{untrusted.system_rule(nonce)}"},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]
    tools = registry.specs_for(spec.tools)
    total_tokens = 0
    for step in range(1, max_steps + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _RunAbort(RunStatus.TIMED_OUT, E.AGT_E_TIMEOUT)
        started = time.monotonic()
        meta = {"agent": spec.kind, "prompt_version": version, "input_digest": run.input_digest, "step_seq": step}
        result = _chat_with_retry(messages, tools, max_tokens=1024, timeout=min(30.0, remaining), meta=meta, deadline=deadline)
        run.step_count = step
        run.tokens_in += result.tokens_in
        run.tokens_out += result.tokens_out
        run.model_name = result.model or run.model_name
        total_tokens += result.tokens_in + result.tokens_out
        _record_usage(run, spec, result)
        _record_step(run, step * 10, StepKind.MODEL, result={"finish": result.finish_reason, "tool_calls": len(result.tool_calls)},
                     duration_ms=(time.monotonic() - started) * 1000, tokens_in=result.tokens_in, tokens_out=result.tokens_out)
        if total_tokens > token_cap:
            raise _RunAbort(RunStatus.BUDGET_EXCEEDED, E.AGT_E_BUDGET)
        if not result.tool_calls:
            return spec.parse_final(tctx, context, result.text), result.text
        messages.append({
            "role": "assistant", "content": result.text,
            "tool_calls": [{"id": c.id, "name": c.name, "arguments": c.arguments} for c in result.tool_calls],
        })
        for i, call in enumerate(result.tool_calls):
            t0 = time.monotonic()
            if i >= max_calls:
                payload = {"error": "Too many tool calls in one step; this call was skipped."}
                kind = StepKind.POLICY_DENY
            else:
                try:
                    payload = registry.invoke(call.name, call.arguments, tctx, allowlist=spec.tools)
                    kind = StepKind.TOOL
                except BusinessRuleError as exc:
                    payload = {"error": str(exc.detail)[:300]}
                    kind = StepKind.POLICY_DENY
            _record_step(run, step * 10 + 1 + i, kind, tool_name=call.name, args=call.arguments, result=payload,
                         duration_ms=(time.monotonic() - t0) * 1000)
            body = json.dumps(redaction.redact(payload), default=str)[:_MAX_TOOL_RESULT_CHARS]
            messages.append({"role": "tool", "tool_call_id": call.id, "name": call.name, "content": body})
    raise _RunAbort(RunStatus.FAILED, E.AGT_E_STEP_LIMIT)


def _valid_drafts(spec: AgentSpec, tctx, context: dict, drafts: list[dict]) -> list[dict]:
    """Rules-only drafts are checked one by one: a sweep over many documents must not lose every draft because one
    document is odd. If none passes, the first error ends the run as before."""
    good, first_error = [], None
    for d in drafts:
        try:
            spec.validate(tctx, context, [d])
            good.append(d)
        except BusinessRuleError as exc:
            first_error = first_error or exc
            logger.info("agents: skipped one draft that failed validation (%s)", exc)
    if drafts and not good and first_error is not None:
        raise first_error
    return good


def _create_each(run: AgentRun, drafts: list[dict]) -> list[int]:
    """Persist drafts one at a time for the same reason; the run fails only if every draft is refused."""
    ids, first_error = [], None
    for d in drafts:
        try:
            ids.extend(p.pk for p in services.create_proposals(run, [d], assignee=None))
        except BusinessRuleError as exc:
            first_error = first_error or exc
            logger.warning("agents: run %s skipped one draft that could not be saved (%s)", run.pk, exc)
    if drafts and not ids and first_error is not None:
        raise first_error
    return ids


def run_agent(run: AgentRun, extras: dict | None = None) -> AgentRun:
    """Execute one run to a terminal status. Never raises for expected failures; they are recorded on the run.

    ``extras`` carries per-call input that must not be stored on the run (pasted order text); hooks read it
    from ``tctx.extras``."""
    spec = get_agent(run.agent)
    company = run.company
    run.status, run.started_at = RunStatus.RUNNING, timezone.now()
    run.save(update_fields=["status", "started_at", "updated_at"])
    deadline = time.monotonic() + spec.limit("run_timeout_s", settings.AGENTS["RUN_TIMEOUT_S"])
    try:
        policy.assert_enabled(company, spec)
        tctx = registry.ToolContext(company=company, company_user=_company_user_for(run), run=run, as_of=timezone.localdate(), extras=dict(extras or {}))
        context = spec.context_builder(tctx)
        run.input_digest = canonical_digest(context.get("facts", {}))
        decision = policy.llm_decision(company)
        drafts: list[dict] | None = None
        use_llm = decision.allow_llm and not context.get("rules_only")
        if use_llm:
            try:
                drafts, _text = _llm_drafts(run, spec, tctx, context, deadline)
                spec.validate(tctx, context, drafts)
            except _RunAbort as abort:
                if abort.code == E.AGT_E_PROVIDER:
                    drafts = None  # provider down: degrade to rules-only below
                else:
                    raise
            except (BusinessRuleError, ValueError, KeyError, TypeError) as exc:
                logger.info("agents: draft rejected, falling back to rules-only (%s)", exc)
                drafts = None
        if drafts is None:
            run.rules_only = True
            drafts = _valid_drafts(spec, tctx, context, spec.rules_only(tctx, context))
        # Includes drafts that already existed live for the same key, which this run did not create.
        run.proposal_ids_out = _create_each(run, drafts)
        run.status = RunStatus.SUCCEEDED
    except _RunAbort as abort:
        run.status, run.error_code = abort.status, abort.code
    except BusinessRuleError as exc:
        run.status = RunStatus.FAILED
        run.error_code = (exc.get_codes() if isinstance(exc.get_codes(), str) else E.AGT_E_VALIDATION)[:40]
    except Exception:  # noqa: BLE001 - a run must always end in a terminal status
        logger.exception("agents: run %s crashed", run.pk)
        run.status, run.error_code = RunStatus.FAILED, "AGT_E_INTERNAL"
    run.finished_at = timezone.now()
    run.save()
    if run.status != RunStatus.SUCCEEDED:
        services._telemetry(company, run.requested_by, success=False, feature=f"{run.agent}:run")
    return run


def execute_run(run_id: int, extras: dict | None = None) -> AgentRun | None:
    """Entry point for Celery and the sync path. Skips runs that are no longer QUEUED."""
    run = AgentRun.objects.select_related("company").filter(pk=run_id).first()
    if run is None or run.status != RunStatus.QUEUED:
        return run
    from core.services import ai_spend

    with ai_spend.charging(run.company_id):
        return run_agent(run, extras)
