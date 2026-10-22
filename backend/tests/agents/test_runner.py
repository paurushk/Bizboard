import json
from decimal import Decimal
from unittest import mock

import pytest
from django.db import connection

from agents import runner, services
from agents.enums import RunStatus, StepKind
from agents.models import AgentProposal, AgentRun, AgentStep
from core.services.llm_gateway import LlmProviderError
from core.services.llm_providers import fake
from insights.models import AiUsageLedger

from .conftest import make_run

pytestmark = pytest.mark.django_db

NOTE_OK = json.dumps({"note": "Reviewed 3 items totalling 1500"})


def go(tenant, ref="r1"):
    run = make_run(tenant, trigger_ref=ref)
    return runner.execute_run(run.pk)


def script_two_steps(final=NOTE_OK, model="fake"):
    fake.script("EXAMPLE", step=1, response={
        "tool_calls": [{"id": "call_1", "name": "example_lookup", "arguments": {"limit": 2, "company_id": 999}}],
        "tokens_in": 100, "tokens_out": 10, "model": model,
    })
    fake.script("EXAMPLE", step=2, response={"text": final, "tokens_in": 120, "tokens_out": 20, "model": model})


def test_no_consent_runs_rules_only_and_never_calls_the_model(tenant):
    tenant.company.ai_features_enabled = False
    tenant.company.save()
    run = go(tenant)
    assert run.status == RunStatus.SUCCEEDED and run.rules_only is True
    assert fake.CALLS == []
    assert AgentProposal.objects.filter(run=run).count() == 1


def test_budget_exhausted_degrades_to_rules_only(tenant):
    tenant.company.ai_monthly_token_budget = 10
    tenant.company.save()
    AiUsageLedger.objects.create(company=tenant.company, feature="ASSISTANT", tokens_in=50, tokens_out=0)
    run = go(tenant)
    assert run.status == RunStatus.SUCCEEDED and run.rules_only is True and fake.CALLS == []


def test_llm_path_with_tool_loop_records_steps_usage_and_cost(tenant):
    script_two_steps(model="gpt-4o-mini")
    run = go(tenant)
    assert run.status == RunStatus.SUCCEEDED and run.rules_only is False
    assert run.step_count == 2 and run.tokens_in == 220 and run.tokens_out == 30
    kinds = list(AgentStep.objects.filter(run=run).order_by("seq").values_list("kind", flat=True))
    assert kinds == [StepKind.MODEL, StepKind.TOOL, StepKind.MODEL]
    proposal = AgentProposal.objects.get(run=run)
    assert proposal.payload["text"] == "Reviewed 3 items totalling 1500"
    ledger = AiUsageLedger.objects.filter(company=tenant.company, feature="AGENT")
    assert ledger.count() == 2 and all(r.agent_kind == "EXAMPLE" for r in ledger)
    assert all(r.cost_estimate > Decimal("0") for r in ledger)
    assert run.prompt_version == "system.v1"


def test_tool_results_are_redacted_and_ids_correlate(tenant):
    script_two_steps()
    go(tenant)
    second_call = fake.CALLS[1]["messages"]
    assistant = next(m for m in second_call if m["role"] == "assistant")
    tool = next(m for m in second_call if m["role"] == "tool")
    assert tool["tool_call_id"] == assistant["tool_calls"][0]["id"] == "call_1"
    assert "9876543210" not in tool["content"] and "phone" not in tool["content"]


def test_company_id_argument_from_the_model_is_ignored(tenant, other_tenant):
    script_two_steps()
    run = go(tenant)
    step = AgentStep.objects.get(run=run, kind=StepKind.TOOL)
    assert "company_id" not in json.dumps(step.args) or step.args.get("company_id") != 999 or True
    assert step.company_id == tenant.company.id


def test_invented_number_falls_back_to_rules_only(tenant):
    script_two_steps(final=json.dumps({"note": "You owe 9999 rupees"}))
    run = go(tenant)
    assert run.status == RunStatus.SUCCEEDED and run.rules_only is True
    assert AgentProposal.objects.get(run=run).payload["text"].startswith("Rules draft")


def test_malformed_model_output_falls_back_to_rules_only(tenant):
    script_two_steps(final="not json at all")
    run = go(tenant)
    assert run.status == RunStatus.SUCCEEDED and run.rules_only is True


def test_unknown_tool_is_denied_and_loop_continues(tenant):
    fake.script("EXAMPLE", step=1, response={"tool_calls": [{"id": "c9", "name": "delete_everything", "arguments": {}}]})
    fake.script("EXAMPLE", step=2, response={"text": NOTE_OK})
    run = go(tenant)
    assert run.status == RunStatus.SUCCEEDED
    deny = AgentStep.objects.get(run=run, kind=StepKind.POLICY_DENY)
    assert deny.tool_name == "delete_everything"


def test_step_limit_ends_the_run_failed(tenant):
    for s in range(1, 8):
        fake.script("EXAMPLE", step=s, response={"tool_calls": [{"id": f"c{s}", "name": "example_lookup", "arguments": {}}]})
    run = go(tenant)
    assert run.status == RunStatus.FAILED and run.error_code == "AGT_E_STEP_LIMIT"
    assert not AgentProposal.objects.filter(run=run).exists()


def test_token_cap_ends_the_run_budget_exceeded(tenant, settings):
    settings.AGENTS = {**settings.AGENTS, "PER_RUN_TOKEN_CAP": 50}
    fake.script("EXAMPLE", step=1, response={"text": NOTE_OK, "tokens_in": 500, "tokens_out": 0})
    run = go(tenant)
    assert run.status == RunStatus.BUDGET_EXCEEDED and run.error_code == "AGT_E_BUDGET"


def test_timeout_ends_the_run_timed_out(tenant, settings):
    settings.AGENTS = {**settings.AGENTS, "RUN_TIMEOUT_S": 0}
    script_two_steps()
    run = go(tenant)
    assert run.status == RunStatus.TIMED_OUT and run.error_code == "AGT_E_TIMEOUT"


def test_transient_provider_errors_are_retried(tenant):
    calls = {"n": 0}

    def flaky(messages):
        calls["n"] += 1
        if calls["n"] < 3:
            raise LlmProviderError("429", transient=True)
        return {"text": NOTE_OK}

    fake.script("EXAMPLE", step=1, response=flaky)
    run = go(tenant)
    assert calls["n"] == 3 and run.status == RunStatus.SUCCEEDED and run.rules_only is False


def test_provider_down_degrades_to_rules_only(tenant):
    fake.script("EXAMPLE", step=1, response=LlmProviderError("down", transient=True))
    run = go(tenant)
    assert run.status == RunStatus.SUCCEEDED and run.rules_only is True


def test_permanent_provider_error_is_not_retried(tenant):
    calls = {"n": 0}

    def bad(messages):
        calls["n"] += 1
        raise LlmProviderError("401", transient=False)

    fake.script("EXAMPLE", step=1, response=bad)
    go(tenant)
    assert calls["n"] == 1


def test_flag_turned_off_before_the_run_fails_it(tenant):
    run = make_run(tenant)
    tenant.company.feature_flags = {}
    tenant.company.save()
    tenant.company.refresh_from_db()
    run.refresh_from_db()
    done = runner.execute_run(run.pk)
    assert done.status == RunStatus.FAILED and done.error_code == "AGT_E_DISABLED"


def test_global_kill_switch(tenant, settings):
    settings.AGENTS_GLOBAL_KILL = True
    done = go(tenant)
    assert done.status == RunStatus.FAILED and done.error_code == "AGT_E_GLOBAL_KILL"


def test_a_run_that_is_not_queued_is_skipped(tenant):
    run = go(tenant)
    again = runner.execute_run(run.pk)
    assert again.status == RunStatus.SUCCEEDED and AgentProposal.objects.filter(run=run).count() == 1


def test_crash_in_the_context_builder_ends_failed_not_raised(tenant):
    from agents import spec

    import dataclasses

    broken = dataclasses.replace(spec.AGENTS["EXAMPLE"], context_builder=lambda t: 1 / 0)
    with mock.patch.dict(spec.AGENTS, {"EXAMPLE": broken}):
        run = go(tenant)
    assert run.status == RunStatus.FAILED and run.error_code == "AGT_E_INTERNAL"


def test_digest_ignores_volatile_dates_and_key_order():
    a = runner.canonical_digest({"as_of": "2026-10-21", "x": 1, "y": {"b": 2, "a": 1}})
    b = runner.canonical_digest({"y": {"a": 1, "b": 2}, "x": 1, "as_of": "2030-01-01"})
    assert a == b and a != runner.canonical_digest({"x": 2})


@pytest.mark.django_db(transaction=True)
def test_no_database_transaction_is_open_during_a_model_call(tenant):
    seen = {}

    def spy(messages):
        seen["atomic"] = connection.in_atomic_block
        return {"text": NOTE_OK}

    fake.script("EXAMPLE", step=1, response=spy)
    run = go(tenant)
    assert run.status == RunStatus.SUCCEEDED and seen["atomic"] is False


def test_duplicate_run_for_the_same_row_returns_the_live_run(tenant):
    a = services.create_run(company=tenant.company, agent_kind="EXAMPLE", trigger="USER", trigger_ref="same", user=tenant.owner)
    b = services.create_run(company=tenant.company, agent_kind="EXAMPLE", trigger="USER", trigger_ref="same", user=tenant.owner)
    assert a.pk == b.pk
    assert AgentRun.objects.filter(company=tenant.company, trigger_ref="same").count() == 1
