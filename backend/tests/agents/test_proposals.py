import dataclasses
from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from agents import services, spec
from agents.enums import ALLOWED_TRANSITIONS, ProposalStatus
from agents.models import AgentProposal
from core.exceptions import BusinessRuleError

from .conftest import make_proposal, owner_cu, staff_cu

pytestmark = pytest.mark.django_db


def approve(tenant, p, revision=None, cu=None):
    return services.approve_proposal(
        company=tenant.company, company_user=cu or owner_cu(tenant), proposal_id=p.pk,
        revision=p.revision if revision is None else revision,
    )


def code_of(exc):
    return exc.get_codes()


# --- state machine -----------------------------------------------------------------------------
@pytest.mark.parametrize("src", list(ProposalStatus))
@pytest.mark.parametrize("dst", list(ProposalStatus))
def test_transition_table_rejects_every_illegal_move(tenant, src, dst):
    p = make_proposal(tenant, dedupe=f"t-{src}-{dst}")
    p.status = src
    if dst in ALLOWED_TRANSITIONS[src]:
        services._move(p, dst)
        assert p.status == dst
    else:
        with pytest.raises(BusinessRuleError) as exc:
            services._move(p, dst)
        assert code_of(exc.value) == "AGT_E_BAD_TRANSITION" and exc.value.status_code == 409


# --- approve ----------------------------------------------------------------------------------
def test_approve_executes_once_with_revision_salted_reference_and_execution_date(tenant):
    p = make_proposal(tenant)
    done = approve(tenant, p)
    assert done.status == ProposalStatus.EXECUTED and done.attempts == 1
    assert done.result_ref["ref"] == f"{p.idempotency_key}:r0"
    assert done.result_ref["date"] == timezone.localdate().isoformat()
    assert done.decided_by_id == tenant.owner.id


def test_second_approve_is_a_conflict_and_does_not_run_again(tenant):
    p = make_proposal(tenant)
    first = approve(tenant, p)
    with pytest.raises(BusinessRuleError) as exc:
        approve(tenant, p)
    assert exc.value.status_code == 409 and code_of(exc.value) == "AGT_E_BAD_TRANSITION"
    p.refresh_from_db()
    assert p.result_ref == first.result_ref and p.attempts == 1


def test_wrong_revision_is_refused_and_leaves_the_draft_pending(tenant):
    p = make_proposal(tenant)
    with pytest.raises(BusinessRuleError) as exc:
        approve(tenant, p, revision=5)
    assert code_of(exc.value) == "AGT_E_REVISION" and exc.value.status_code == 409
    p.refresh_from_db()
    assert p.status == ProposalStatus.PENDING and p.attempts == 0


def test_role_without_approve_permission_is_refused(tenant):
    p = make_proposal(tenant)
    with pytest.raises(BusinessRuleError) as exc:
        approve(tenant, p, cu=staff_cu(tenant))
    assert code_of(exc.value) == "AGT_E_ROLE"
    p.refresh_from_db()
    assert p.status == ProposalStatus.PENDING


def test_stale_failure_is_recorded_and_terminal(tenant):
    p = make_proposal(tenant, fail="stale")
    with pytest.raises(BusinessRuleError) as exc:
        approve(tenant, p)
    assert code_of(exc.value) == "AGT_E_STALE" and exc.value.status_code == 409
    p.refresh_from_db()
    assert p.status == ProposalStatus.FAILED and p.failure_code == "STALE" and p.attempts == 1
    with pytest.raises(BusinessRuleError):
        services.retry_proposal(company=tenant.company, company_user=owner_cu(tenant), proposal_id=p.pk, revision=0)
    with pytest.raises(BusinessRuleError):
        services.edit_proposal(company=tenant.company, company_user=owner_cu(tenant), proposal_id=p.pk, edited_payload={"text": "x"}, revision=0)


def test_business_rule_failure_is_recorded_then_edit_reopens_and_succeeds(tenant):
    p = make_proposal(tenant, fail="rule")
    with pytest.raises(BusinessRuleError):
        approve(tenant, p)
    p.refresh_from_db()
    assert p.status == ProposalStatus.FAILED and p.failure_code == "example_rule"
    edited = services.edit_proposal(
        company=tenant.company, company_user=owner_cu(tenant), proposal_id=p.pk,
        edited_payload={"text": "fixed 3 items", "fail": ""}, revision=p.revision,
    )
    assert edited.status == ProposalStatus.PENDING and edited.revision == 1 and edited.failure_code == ""
    done = approve(tenant, edited)
    assert done.status == ProposalStatus.EXECUTED
    assert done.result_ref["ref"].endswith(":r1")  # an edited revision is a new attempt
    assert done.effective_payload["text"] == "fixed 3 items"


def test_retry_at_the_same_revision_after_a_transient_failure(tenant):
    p = make_proposal(tenant)
    kind = spec.PROPOSAL_KINDS["EXAMPLE_NOTE"]
    calls = {"n": 0}

    def flaky(proposal, ctx):
        calls["n"] += 1
        if calls["n"] == 1:
            raise BusinessRuleError("try later", code="AGT_E_PROVIDER")
        return {"type": "ok", "ref": ctx.external_ref}

    with mock.patch.dict(spec.PROPOSAL_KINDS, {"EXAMPLE_NOTE": dataclasses.replace(kind, executor=flaky)}):
        with pytest.raises(BusinessRuleError):
            approve(tenant, p)
        p.refresh_from_db()
        assert p.status == ProposalStatus.FAILED and p.failure_code == "AGT_E_PROVIDER"
        done = services.retry_proposal(company=tenant.company, company_user=owner_cu(tenant), proposal_id=p.pk, revision=p.revision)
        assert done.status == ProposalStatus.EXECUTED and done.attempts == 2
        assert done.result_ref["ref"] == f"{p.idempotency_key}:r0"  # same revision, same domain reference


def test_attempts_are_capped(tenant):
    p = make_proposal(tenant, fail="rule")
    with pytest.raises(BusinessRuleError):
        approve(tenant, p)
    for _ in range(2):
        with pytest.raises(BusinessRuleError):
            services.retry_proposal(company=tenant.company, company_user=owner_cu(tenant), proposal_id=p.pk, revision=0)
    p.refresh_from_db()
    assert p.status == ProposalStatus.FAILED and p.attempts == 3
    with pytest.raises(BusinessRuleError) as exc:
        services.retry_proposal(company=tenant.company, company_user=owner_cu(tenant), proposal_id=p.pk, revision=0)
    assert code_of(exc.value) == "AGT_E_ATTEMPTS"


def test_unexpected_executor_exception_is_recorded_failed_and_reraised(tenant):
    p = make_proposal(tenant, fail="boom")
    with pytest.raises(RuntimeError):
        approve(tenant, p)
    p.refresh_from_db()
    assert p.status == ProposalStatus.FAILED and p.failure_code == "EXECUTOR_ERROR"


def test_failed_record_survives_the_executor_rollback(tenant):
    """Block A rolls back its own writes; the FAILED row and audit are written afterwards, in a new block."""
    from accounts.models import Company

    kind = spec.PROPOSAL_KINDS["EXAMPLE_NOTE"]

    def writes_then_fails(proposal, ctx):
        Company.objects.filter(pk=ctx.company.pk).update(name="CHANGED BY EXECUTOR")
        raise BusinessRuleError("nope", code="example_rule")

    p = make_proposal(tenant)
    with mock.patch.dict(spec.PROPOSAL_KINDS, {"EXAMPLE_NOTE": dataclasses.replace(kind, executor=writes_then_fails)}):
        with pytest.raises(BusinessRuleError):
            approve(tenant, p)
    tenant.company.refresh_from_db()
    p.refresh_from_db()
    assert tenant.company.name != "CHANGED BY EXECUTOR"  # executor writes rolled back
    assert p.status == ProposalStatus.FAILED  # the failure record was not


def test_expired_draft_cannot_be_approved_and_the_expiry_persists(tenant):
    p = make_proposal(tenant)
    AgentProposal.objects.filter(pk=p.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
    with pytest.raises(BusinessRuleError) as exc:
        approve(tenant, p)
    assert code_of(exc.value) == "AGT_E_EXPIRED" and exc.value.status_code == 409
    p.refresh_from_db()
    assert p.status == ProposalStatus.EXPIRED


def test_expire_due_only_touches_pending_past_due(tenant):
    old = make_proposal(tenant, dedupe="old")
    fresh = make_proposal(tenant, dedupe="fresh")
    AgentProposal.objects.filter(pk=old.pk).update(expires_at=timezone.now() - timedelta(hours=1))
    assert services.expire_due() == 1
    old.refresh_from_db(), fresh.refresh_from_db()
    assert old.status == ProposalStatus.EXPIRED and fresh.status == ProposalStatus.PENDING


def test_agent_switched_off_after_drafting_blocks_approval_without_a_failed_record(tenant):
    p = make_proposal(tenant)
    tenant.company.feature_flags = {}
    tenant.company.save()
    with pytest.raises(BusinessRuleError) as exc:
        approve(tenant, p)
    assert code_of(exc.value) == "AGT_E_DISABLED"
    p.refresh_from_db()
    assert p.status == ProposalStatus.PENDING and p.attempts == 0


# --- edit / reject / cancel -------------------------------------------------------------------
def test_edit_bumps_revision_and_stale_revision_conflicts(tenant):
    p = make_proposal(tenant)
    e = services.edit_proposal(company=tenant.company, company_user=owner_cu(tenant), proposal_id=p.pk, edited_payload={"text": "new text 3"}, revision=0)
    assert e.revision == 1 and e.effective_payload["text"] == "new text 3" and e.payload["text"] != "new text 3"
    with pytest.raises(BusinessRuleError) as exc:
        services.edit_proposal(company=tenant.company, company_user=owner_cu(tenant), proposal_id=p.pk, edited_payload={"text": "x"}, revision=0)
    assert code_of(exc.value) == "AGT_E_REVISION"
    with pytest.raises(BusinessRuleError):
        approve(tenant, p, revision=0)  # the user must approve the version they saw


def test_edit_validates_the_payload(tenant):
    p = make_proposal(tenant)
    with pytest.raises(BusinessRuleError):
        services.edit_proposal(company=tenant.company, company_user=owner_cu(tenant), proposal_id=p.pk, edited_payload={"text": ""}, revision=0)


def test_reject_records_reason_and_requires_role(tenant):
    p = make_proposal(tenant)
    with pytest.raises(BusinessRuleError):
        services.reject_proposal(company=tenant.company, company_user=staff_cu(tenant), proposal_id=p.pk, reason="x")
    r = services.reject_proposal(company=tenant.company, company_user=owner_cu(tenant), proposal_id=p.pk, reason="not today")
    assert r.status == ProposalStatus.REJECTED and r.decision_note == "not today"
    with pytest.raises(BusinessRuleError):
        approve(tenant, p)


def test_cancel_by_creator_or_manager_only(tenant):
    p = make_proposal(tenant)  # created_by = owner via run.requested_by
    with pytest.raises(BusinessRuleError):
        services.cancel_proposal(company=tenant.company, company_user=staff_cu(tenant), proposal_id=p.pk)
    c = services.cancel_proposal(company=tenant.company, company_user=owner_cu(tenant), proposal_id=p.pk, note="changed mind")
    assert c.status == ProposalStatus.CANCELLED


def test_cancel_live_for_keys_cancels_only_pending(tenant):
    a = make_proposal(tenant, dedupe="a")
    b = make_proposal(tenant, dedupe="b")
    approve(tenant, b)
    assert services.cancel_live_for_keys(tenant.company, "EXAMPLE_NOTE", ["a", "b"]) == 1
    a.refresh_from_db(), b.refresh_from_db()
    assert a.status == ProposalStatus.CANCELLED and b.status == ProposalStatus.EXECUTED


def test_every_transition_writes_an_audit_event(tenant):
    from core.models import AuditEvent

    p = make_proposal(tenant)
    approve(tenant, p)
    actions = set(AuditEvent.objects.filter(company=tenant.company).values_list("action", flat=True))
    assert "agents.proposal.executed" in actions
