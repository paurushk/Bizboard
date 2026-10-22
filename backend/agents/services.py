"""Run and proposal lifecycle. All state changes happen here and nowhere else.

Approve boundaries (plan 3.4):
  view (not atomic) -> wrap_idempotent -> approve_proposal:
    block A  transaction.atomic(): lock -> checks -> re-validate -> executor -> EXECUTED
    on failure: block A rolled back; block B (separate atomic): lock -> FAILED + audit; then re-raise.
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.services.audit import AuditService

from . import error_codes as E
from .enums import (
    ALLOWED_TRANSITIONS,
    MAX_EXECUTE_ATTEMPTS,
    NON_RETRYABLE_FAILURES,
    LIVE_PROPOSAL_STATUSES,
    ProposalStatus,
    RunStatus,
)
from .executors import ExecContext, external_ref
from .models import AgentProposal, AgentRun
from .spec import get_agent, get_kind

logger = logging.getLogger("agents")


# --- audit + telemetry -------------------------------------------------------------------------

def _audit(proposal: AgentProposal, user, event: str, **meta) -> None:
    AuditService.log(
        company=proposal.company,
        user=user,
        action=f"agents.proposal.{event}",
        entity_type="AgentProposal",
        entity_id=proposal.pk,
        description=f"agent proposal {event}: {proposal.kind}"[:240],
        metadata={"kind": proposal.kind, "revision": proposal.revision, "status": proposal.status, **meta},
    )


def _telemetry(company, user, *, success: bool, feature: str, reason: str = "") -> None:
    from insights.telemetry import record_event

    record_event(
        company, "journey_started" if success else "journey_failed", user=user,
        journey="agents", feature=feature[:40], success=success, failure_reason="",
    )


# --- runs --------------------------------------------------------------------------------------

def create_run(*, company, agent_kind: str, trigger: str, trigger_ref: str = "", user=None) -> AgentRun:
    """Create a QUEUED run. One live run per (company, agent, trigger_ref): a duplicate returns that run."""
    get_agent(agent_kind)
    if trigger_ref:
        live = AgentRun.objects.filter(
            company=company, agent=agent_kind, trigger_ref=trigger_ref,
            status__in=[RunStatus.QUEUED, RunStatus.RUNNING],
        ).first()
        if live:
            return live
    try:
        with transaction.atomic():
            return AgentRun.objects.create(
                company=company, agent=agent_kind, trigger=trigger, trigger_ref=trigger_ref,
                requested_by=user, created_by=user, updated_by=user,
            )
    except IntegrityError:
        live = AgentRun.objects.filter(
            company=company, agent=agent_kind, trigger_ref=trigger_ref,
            status__in=[RunStatus.QUEUED, RunStatus.RUNNING],
        ).first()
        if live:
            return live
        raise


# --- proposals: create -------------------------------------------------------------------------

def _validated_payload(kind_spec, payload: dict, version: int) -> dict:
    ser_cls = kind_spec.payload_serializers.get(version)
    if ser_cls is None:
        raise BusinessRuleError(f"No payload serializer for {kind_spec.kind} v{version}", code=E.AGT_E_VALIDATION)
    ser = ser_cls(data=payload)
    if not ser.is_valid():
        raise BusinessRuleError(f"Invalid {kind_spec.kind} payload: {ser.errors}", code=E.AGT_E_VALIDATION)
    return _jsonable(ser.validated_data)


def _jsonable(value):
    from decimal import Decimal
    from datetime import date, datetime

    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def create_proposals(run: AgentRun, drafts: list[dict], *, assignee=None) -> list[AgentProposal]:
    """Persist validated drafts. A live proposal with the same (kind, dedupe_key) is returned, not duplicated."""
    spec = get_agent(run.agent)
    allowed = {k.kind for k in spec.proposal_kinds}
    out: list[AgentProposal] = []
    now = timezone.now()
    for d in drafts:
        kind_spec = get_kind(d["kind"])
        if kind_spec.kind not in allowed:
            raise BusinessRuleError(f"Agent {spec.kind} cannot produce {kind_spec.kind}", code=E.AGT_E_UNKNOWN_KIND)
        if not d.get("evidence"):
            raise BusinessRuleError("A proposal needs at least one evidence entry.", code=E.AGT_E_VALIDATION)
        version = kind_spec.current_version
        payload = _validated_payload(kind_spec, d["payload"], version)
        existing = AgentProposal.objects.filter(
            company=run.company, kind=kind_spec.kind, dedupe_key=d["dedupe_key"],
            status__in=[s.value for s in LIVE_PROPOSAL_STATUSES],
        ).first()
        if existing:
            out.append(existing)
            continue
        try:
            with transaction.atomic():
                out.append(AgentProposal.objects.create(
                    company=run.company, run=run, kind=kind_spec.kind, autonomy=kind_spec.autonomy,
                    title=str(d["title"])[:160], payload=payload, schema_version=version,
                    evidence=d["evidence"], dedupe_key=d["dedupe_key"][:255],
                    group_key=(d.get("group_key") or "")[:255],
                    expires_at=now + timedelta(hours=kind_spec.default_ttl_hours),
                    idempotency_key=uuid.uuid4().hex, assignee=d.get("assignee") or assignee,
                    created_by=run.requested_by, updated_by=run.requested_by,
                ))
        except IntegrityError:
            # Lost a race to another run for the same key: return the winner.
            winner = AgentProposal.objects.filter(
                company=run.company, kind=kind_spec.kind, dedupe_key=d["dedupe_key"],
                status__in=[s.value for s in LIVE_PROPOSAL_STATUSES],
            ).first()
            if winner is None:
                raise
            out.append(winner)
    return out


# --- proposals: transitions --------------------------------------------------------------------

def _locked(company, proposal_id: int) -> AgentProposal:
    try:
        return AgentProposal.objects.select_for_update().select_related("company").get(pk=proposal_id, company=company)
    except AgentProposal.DoesNotExist:
        raise BusinessRuleError("Draft not found.", code=E.AGT_E_VALIDATION) from None


def _move(p: AgentProposal, new: str) -> None:
    if new not in ALLOWED_TRANSITIONS.get(p.status, set()):
        raise E.conflict(f"Cannot move a {p.status} draft to {new}.", E.AGT_E_BAD_TRANSITION)
    p.status = new


def _check_revision(p: AgentProposal, revision) -> None:
    if revision is None or int(revision) != p.revision:
        raise E.conflict("This draft was changed. Reload it and review the latest version.", E.AGT_E_REVISION)


def edit_proposal(*, company, company_user, proposal_id: int, edited_payload: dict, revision: int) -> AgentProposal:
    from . import policy

    with transaction.atomic():
        p = _locked(company, proposal_id)
        kind_spec = get_kind(p.kind)
        policy.assert_can_approve(company_user, kind_spec)
        _check_revision(p, revision)
        if p.status == ProposalStatus.FAILED:
            if p.failure_code in NON_RETRYABLE_FAILURES:
                raise E.conflict("This draft is stale; prepare it again.", E.AGT_E_STALE)
            if p.attempts >= MAX_EXECUTE_ATTEMPTS:
                raise E.conflict("Too many failed attempts.", E.AGT_E_ATTEMPTS)
            _move(p, ProposalStatus.PENDING)
        elif p.status != ProposalStatus.PENDING:
            raise E.conflict(f"A {p.status} draft cannot be edited.", E.AGT_E_BAD_TRANSITION)
        p.edited_payload = _validated_payload(kind_spec, edited_payload, p.schema_version)
        p.revision += 1
        p.failure_code = ""
        p.updated_by = company_user.user
        p.save()
        _audit(p, company_user.user, "edited")
    return p


def reject_proposal(*, company, company_user, proposal_id: int, reason: str = "") -> AgentProposal:
    from . import policy

    with transaction.atomic():
        p = _locked(company, proposal_id)
        policy.assert_can_approve(company_user, get_kind(p.kind))
        _move(p, ProposalStatus.REJECTED)
        p.decided_by, p.decided_at, p.decision_note = company_user.user, timezone.now(), reason[:500]
        p.updated_by = company_user.user
        p.save()
        _audit(p, company_user.user, "rejected", reason=reason[:200])
    _telemetry(company, company_user.user, success=True, feature=f"{p.kind}:rejected")
    return p


def cancel_proposal(*, company, company_user, proposal_id: int, note: str = "") -> AgentProposal:
    with transaction.atomic():
        p = _locked(company, proposal_id)
        is_manager = company_user.role in ("OWNER", "MANAGER")
        if not is_manager and p.created_by_id != company_user.user_id:
            raise BusinessRuleError("Only the creator or a manager can cancel.", code=E.AGT_E_ROLE)
        _move(p, ProposalStatus.CANCELLED)
        p.decided_by, p.decided_at, p.decision_note = company_user.user, timezone.now(), note[:500]
        p.save()
        _audit(p, company_user.user, "cancelled", note=note[:200])
    return p


def approve_proposal(*, company, company_user, proposal_id: int, revision: int) -> AgentProposal:
    """Approve and execute exactly the revision the user saw. See module docstring for boundaries."""
    from . import policy

    outcome = None  # ("expired",) set inside block A so the EXPIRED write commits
    try:
        with transaction.atomic():
            p = _locked(company, proposal_id)
            kind_spec = get_kind(p.kind)
            policy.assert_can_approve(company_user, kind_spec)
            policy.assert_kind_executable(kind_spec, p.autonomy)
            if p.status != ProposalStatus.PENDING:
                raise E.conflict(f"A {p.status} draft cannot be approved.", E.AGT_E_BAD_TRANSITION)
            _check_revision(p, revision)
            if p.expires_at <= timezone.now():
                _move(p, ProposalStatus.EXPIRED)
                p.save(update_fields=["status", "updated_at"])
                _audit(p, company_user.user, "expired")
                outcome = "expired"
            else:
                spec_agent = get_agent(p.run.agent)
                policy.assert_enabled(company, spec_agent)
                _move(p, ProposalStatus.APPROVED)
                p.decided_by, p.decided_at = company_user.user, timezone.now()
                p.attempts += 1
                p.save()
                ctx = ExecContext(company=company, company_user=company_user, today=timezone.localdate(), external_ref=external_ref(p))
                result_ref = kind_spec.executor(p, ctx) if kind_spec.executor else {"type": "none"}
                p.result_ref = result_ref
                p.failure_code = ""
                _move(p, ProposalStatus.EXECUTED)
                p.updated_by = company_user.user
                p.save()
                _audit(p, company_user.user, "executed", result_ref=result_ref)
    except Exception as exc:  # noqa: BLE001 - any executor failure must leave a FAILED record
        code = _exception_code(exc)
        if _reached_executor(code):
            _mark_failed(company, company_user, proposal_id, code, str(getattr(exc, "detail", exc))[:300])
        raise
    if outcome == "expired":
        raise E.conflict("This draft expired. Prepare it again.", E.AGT_E_EXPIRED)
    _telemetry(company, company_user.user, success=True, feature=f"{p.kind}:executed")
    return p


_PRE_EXECUTION_CODES = {
    E.AGT_E_BAD_TRANSITION, E.AGT_E_REVISION, E.AGT_E_ROLE, E.AGT_E_DISABLED, E.AGT_E_GLOBAL_KILL,
    E.AGT_E_EXPIRED, E.AGT_E_ATTEMPTS,
}


def _exception_code(exc) -> str:
    getter = getattr(exc, "get_codes", None)
    if callable(getter):
        codes = getter()
        if isinstance(codes, str):
            return codes
    return "EXECUTOR_ERROR"


def _reached_executor(code: str) -> bool:
    """FAILED is only recorded when the draft actually entered APPROVED (i.e. the executor ran)."""
    return code not in _PRE_EXECUTION_CODES


def _mark_failed(company, company_user, proposal_id: int, code: str, message: str) -> None:
    """Block B: runs after block A rolled back, in its own transaction."""
    with transaction.atomic():
        try:
            p = AgentProposal.objects.select_for_update().get(pk=proposal_id, company=company)
        except AgentProposal.DoesNotExist:
            return
        if p.status == ProposalStatus.EXECUTED:
            return
        if p.status == ProposalStatus.PENDING:
            # Block A rolled back the PENDING -> APPROVED step, so walk the table to record the failure.
            p.status = ProposalStatus.APPROVED
            p.attempts += 1
        _move(p, ProposalStatus.FAILED)
        p.failure_code = ("STALE" if code == E.AGT_E_STALE else code)[:40]
        p.decision_note = message
        p.save()
        _audit(p, company_user.user, "failed", failure_code=p.failure_code)
    _telemetry(company, company_user.user, success=False, feature=f"{p.kind}:failed")


def retry_proposal(*, company, company_user, proposal_id: int, revision: int) -> AgentProposal:
    """FAILED (non-stale) -> PENDING at the same revision, then approve again."""
    from . import policy

    with transaction.atomic():
        p = _locked(company, proposal_id)
        policy.assert_can_approve(company_user, get_kind(p.kind))
        _check_revision(p, revision)
        if p.status != ProposalStatus.FAILED:
            raise E.conflict("Only a failed draft can be retried.", E.AGT_E_BAD_TRANSITION)
        if p.failure_code in NON_RETRYABLE_FAILURES:
            raise E.conflict("This draft is stale; prepare it again.", E.AGT_E_STALE)
        if p.attempts >= MAX_EXECUTE_ATTEMPTS:
            raise E.conflict("Too many failed attempts.", E.AGT_E_ATTEMPTS)
        _move(p, ProposalStatus.PENDING)
        p.save(update_fields=["status", "updated_at"])
    return approve_proposal(company=company, company_user=company_user, proposal_id=proposal_id, revision=revision)


def expire_due(now=None, company=None, company_id=None) -> int:
    """Move PENDING drafts past expires_at to EXPIRED. Returns how many."""
    now = now or timezone.now()
    qs = AgentProposal.objects.filter(status=ProposalStatus.PENDING, expires_at__lte=now)
    if company is not None:
        qs = qs.filter(company=company)
    if company_id is not None:
        qs = qs.filter(company_id=company_id)
    n = 0
    for pid in list(qs.values_list("pk", flat=True)):
        with transaction.atomic():
            p = AgentProposal.objects.select_for_update().filter(pk=pid, status=ProposalStatus.PENDING).first()
            if p is None:
                continue
            p.status = ProposalStatus.EXPIRED
            p.save(update_fields=["status", "updated_at"])
            _audit(p, None, "expired")
            n += 1
    return n


def cancel_live_for_keys(company, kind: str, dedupe_keys, note: str = "condition resolved") -> int:
    """Cancel PENDING drafts whose attention row has cleared."""
    n = 0
    for p in AgentProposal.objects.filter(company=company, kind=kind, dedupe_key__in=list(dedupe_keys), status=ProposalStatus.PENDING):
        with transaction.atomic():
            p = AgentProposal.objects.select_for_update().get(pk=p.pk)
            if p.status != ProposalStatus.PENDING:
                continue
            p.status = ProposalStatus.CANCELLED
            p.decision_note = note
            p.save(update_fields=["status", "decision_note", "updated_at"])
            _audit(p, None, "cancelled", note=note)
            n += 1
    return n
