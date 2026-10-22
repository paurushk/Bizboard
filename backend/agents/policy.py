"""Who may run or approve what, and when the LLM may be used. Everything fails closed."""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.services.feature_flags import flag_enabled

from . import error_codes as E
from .enums import Autonomy
from .spec import AgentSpec, ProposalKindSpec, get_agent, get_kind


@dataclass
class RunDecision:
    allow_llm: bool
    reason: str = ""          # why the LLM is not allowed (consent, budget, ...), for the run record


def global_kill() -> bool:
    return bool(getattr(settings, "AGENTS_GLOBAL_KILL", False))


def agent_enabled(company, spec: AgentSpec) -> bool:
    if global_kill() or company is None:
        return False
    if not flag_enabled(company, "ENABLE_AGENTS"):
        return False
    if not flag_enabled(company, spec.flag):
        return False
    return all(flag_enabled(company, f) for f in spec.requires_flags)


def assert_enabled(company, spec: AgentSpec) -> None:
    if global_kill():
        raise BusinessRuleError("Agents are switched off.", code=E.AGT_E_GLOBAL_KILL)
    if not agent_enabled(company, spec):
        raise BusinessRuleError("This agent is not enabled for your company.", code=E.AGT_E_DISABLED)


def can_prepare(company_user, spec: AgentSpec) -> bool:
    check = spec.prepare_permission
    return bool(check is not None and check(company_user))


def assert_can_prepare(company_user, spec: AgentSpec) -> None:
    if company_user is None or not can_prepare(company_user, spec):
        raise BusinessRuleError("Your role cannot prepare this draft.", code=E.AGT_E_ROLE)


def can_approve(company_user, kind: ProposalKindSpec) -> bool:
    check = kind.approve_permission
    return bool(company_user is not None and check is not None and check(company_user))


def assert_can_approve(company_user, kind: ProposalKindSpec) -> None:
    if not can_approve(company_user, kind):
        raise BusinessRuleError("Your role cannot approve this draft.", code=E.AGT_E_ROLE)


def assert_kind_executable(kind: ProposalKindSpec, autonomy: int) -> None:
    """L3 (auto-send) is only valid for kinds that opt in; nothing here is ever a money kind."""
    if autonomy >= Autonomy.L3 and kind.autonomy < Autonomy.L3:
        raise BusinessRuleError("This kind cannot run at L3.", code=E.AGT_E_ROLE)


def daily_run_count(company, agent_kind: str) -> int:
    from .models import AgentRun

    today = timezone.localdate()
    return AgentRun.objects.filter(company=company, agent=agent_kind, created_at__date=today).count()


def assert_under_daily_cap(company, spec: AgentSpec) -> None:
    cap = spec.limit("per_company_daily_runs", settings.AGENTS["PER_COMPANY_DAILY_RUNS"])
    if daily_run_count(company, spec.kind) >= cap:
        raise BusinessRuleError("Daily agent run limit reached for this company.", code=E.AGT_E_DAILY_CAP)


def llm_decision(company) -> RunDecision:
    """May this run call a model? No consent or no budget degrades to rules-only; it is not an error."""
    if not getattr(company, "ai_features_enabled", False):
        return RunDecision(False, E.AGT_E_NO_CONSENT)
    from insights.assistant import assert_within_budget

    try:
        assert_within_budget(company)
    except BusinessRuleError:
        return RunDecision(False, E.AGT_E_BUDGET)
    from core.services import ai_spend

    # WP-I1: today's company / platform cap or the global kill switch also mean rules-only.
    if not ai_spend.would_allow(company.pk, 1024):
        return RunDecision(False, E.AGT_E_BUDGET)
    return RunDecision(True)


def check_start(company, company_user, agent_kind: str) -> AgentSpec:
    """Everything a user-triggered start must pass before a run row is created."""
    spec = get_agent(agent_kind)
    assert_enabled(company, spec)
    assert_can_prepare(company_user, spec)
    assert_under_daily_cap(company, spec)
    return spec


def kind_spec(kind: str) -> ProposalKindSpec:
    return get_kind(kind)
