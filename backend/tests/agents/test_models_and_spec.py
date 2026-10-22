import pytest
from django.db import IntegrityError, transaction

from agents import spec
from agents.enums import ProposalStatus, RunStatus
from agents.models import AgentAlias, AgentProposal, AgentRun, AgentStep
from core.exceptions import BusinessRuleError

from .conftest import make_proposal, make_run

pytestmark = pytest.mark.django_db


def test_one_live_run_per_trigger_ref(tenant):
    from agents import services

    first = make_run(tenant, trigger_ref="row-1")
    again = services.create_run(company=tenant.company, agent_kind="EXAMPLE", trigger="USER", trigger_ref="row-1", user=tenant.owner)
    assert again.pk == first.pk
    first.status = RunStatus.SUCCEEDED
    first.save()
    assert make_run(tenant, trigger_ref="row-1").pk != first.pk


def test_db_constraint_blocks_second_live_run(tenant):
    make_run(tenant, trigger_ref="row-2")
    with pytest.raises(IntegrityError), transaction.atomic():
        AgentRun.objects.create(company=tenant.company, agent="EXAMPLE", trigger="USER", trigger_ref="row-2")


def test_one_live_proposal_per_dedupe_key_and_reuse(tenant):
    a = make_proposal(tenant, dedupe="same")
    b = make_proposal(tenant, dedupe="same", run=a.run)
    assert a.pk == b.pk
    with pytest.raises(IntegrityError), transaction.atomic():
        AgentProposal.objects.create(
            company=tenant.company, run=a.run, kind="EXAMPLE_NOTE", title="x", payload={}, evidence=[], dedupe_key="same",
            expires_at=a.expires_at, idempotency_key="z",
        )


def test_terminal_proposal_frees_the_key(tenant):
    a = make_proposal(tenant, dedupe="reuse")
    a.status = ProposalStatus.REJECTED
    a.save()
    b = make_proposal(tenant, dedupe="reuse", run=a.run)
    assert b.pk != a.pk


def test_step_company_must_match_run(tenant, other_tenant):
    run = make_run(tenant)
    with pytest.raises(BusinessRuleError):
        AgentStep.objects.create(company=other_tenant.company, run=run, seq=1, kind="MODEL")


def test_alias_needs_exactly_one_target(tenant):
    with pytest.raises(IntegrityError), transaction.atomic():
        AgentAlias.objects.create(company=tenant.company, scope="CUSTOMER", raw_text_norm="ravi")


def test_proposal_requires_evidence_and_valid_payload(tenant):
    from agents import services

    run = make_run(tenant)
    with pytest.raises(BusinessRuleError):
        services.create_proposals(run, [{"kind": "EXAMPLE_NOTE", "title": "t", "dedupe_key": "e", "payload": {"text": "x"}, "evidence": []}])
    with pytest.raises(BusinessRuleError):
        services.create_proposals(run, [{"kind": "EXAMPLE_NOTE", "title": "t", "dedupe_key": "e2", "payload": {}, "evidence": [{"a": 1}]}])


def test_unknown_agent_and_kind_are_refused(tenant):
    with pytest.raises(BusinessRuleError):
        spec.get_agent("NOPE")
    with pytest.raises(BusinessRuleError):
        spec.get_kind("NOPE")


def test_duplicate_kind_and_bad_flag_fail_registration(example_agent):
    import dataclasses

    ex = example_agent
    with pytest.raises(spec.SpecError):
        spec.register(ex.AGENT)
    bad_flag = dataclasses.replace(ex.AGENT, kind="BADFLAG", flag="NOT_AGENT_FLAG", proposal_kinds=[])
    with pytest.raises(spec.SpecError):
        spec.register(bad_flag)
    unknown_tool = dataclasses.replace(ex.AGENT, kind="BADTOOL", proposal_kinds=[], tools=["does_not_exist"])
    with pytest.raises(spec.SpecError):
        spec.register(unknown_tool)


def test_autodiscover_skips_underscore_packages():
    spec.autodiscover()
    assert "EXAMPLE" not in spec.AGENTS


def test_matches_code_supports_prefix(example_agent):
    s = spec.AGENTS["EXAMPLE"]
    assert s.matches_code("EXAMPLE_ONE") and s.matches_code("AR_OVERDUE_CUSTOMER") and not s.matches_code("OTHER")
