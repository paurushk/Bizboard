"""Agents API (plan section 4). Approve-class POSTs run under wrap_idempotent; the client sends a fresh
Idempotency-Key per user attempt (an edit or a retry after failure is always a new key)."""

from __future__ import annotations

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.permissions import SubscriptionWritesAllowed
from core.exceptions import BusinessRuleError
from core.idempotency import wrap_idempotent
from core.permissions import HasCompany, get_company_user

from . import error_codes as E
from . import policy, services
from .enums import ProposalStatus, Trigger
from .models import AgentProposal, AgentRun
from .serializers import (
    AgentProposalSerializer,
    AgentRunSerializer,
    BulkApproveSerializer,
    EditProposalSerializer,
    RejectSerializer,
    RevisionSerializer,
    StartRunSerializer,
)
from .spec import AGENTS, PROPOSAL_KINDS

SCOPE_RUN_START = "agent_run_start"
SCOPE_APPROVE = "agent_proposal_approve"
SCOPE_BULK_APPROVE = "agent_proposal_bulk_approve"


class AgentsBaseView(APIView):
    permission_classes = [IsAuthenticated, HasCompany]

    def get_permissions(self):
        return [*super().get_permissions(), SubscriptionWritesAllowed()]

    @property
    def company_user(self):
        return get_company_user(self.request)

    @property
    def company(self):
        return self.company_user.company

    def _serializer_context(self):
        return {"company_user": self.company_user, "request": self.request}

    def _gate(self):
        """Master switch and kill switch; per-agent checks happen where the agent is known."""
        if policy.global_kill():
            raise BusinessRuleError("Agents are switched off.", code=E.AGT_E_GLOBAL_KILL)
        enabled_any = [s for s in AGENTS.values() if policy.agent_enabled(self.company, s)]
        if not enabled_any:
            raise BusinessRuleError("Agents are not enabled for your company.", code=E.AGT_E_DISABLED)
        return enabled_any

    def _forbidden(self, exc: BusinessRuleError):
        code = exc.get_codes() if isinstance(exc.get_codes(), str) else ""
        http = status.HTTP_403_FORBIDDEN if code in (E.AGT_E_DISABLED, E.AGT_E_GLOBAL_KILL, E.AGT_E_ROLE) else None
        if http:
            exc.status_code = http
        return exc


class CatalogView(AgentsBaseView):
    """What the UI renders from: agents this user can use, their trigger codes and proposal renderers."""

    def get(self, request):
        cu = self.company_user
        out = []
        for spec in AGENTS.values():
            if not policy.agent_enabled(self.company, spec):
                continue
            out.append({
                "kind": spec.kind,
                "title_key": spec.title_key,
                "trigger_codes": spec.trigger_codes,
                "can_prepare": policy.can_prepare(cu, spec),
                "proposal_kinds": [
                    {
                        "kind": k.kind,
                        "renderer": k.renderer,
                        "bulk_approvable": k.bulk_approvable,
                        "title_key": k.title_key,
                        "can_approve": policy.can_approve(cu, k),
                    }
                    for k in spec.proposal_kinds
                ],
            })
        return Response({"agents": out})


class RunListCreateView(AgentsBaseView):
    def post(self, request):
        ser = StartRunSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        company, cu = self.company, self.company_user
        try:
            spec = policy.check_start(company, cu, ser.validated_data["agent"])
        except BusinessRuleError as exc:
            raise self._forbidden(exc)

        text = (ser.validated_data.get("text") or "").strip()
        if spec.accepts_text:
            if not text:
                raise BusinessRuleError("Paste the text to read.", code=E.AGT_E_VALIDATION)
            if len(text) > spec.text_max_chars:
                raise BusinessRuleError(f"That text is too long (limit {spec.text_max_chars} characters).", code=E.AGT_E_VALIDATION)
        elif text:
            raise BusinessRuleError("This agent does not take pasted text.", code=E.AGT_E_VALIDATION)

        def build_from_text():
            # The person waits for the draft. The text is handed to the run in memory only; the run keeps a hash.
            import hashlib

            from .runner import execute_run

            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]
            run = services.create_run(
                company=company, agent_kind=spec.kind, trigger=Trigger.USER, trigger_ref=f"TEXT:{digest}", user=request.user,
            )
            run = execute_run(run.pk, {"text": text}) or run
            data = AgentRunSerializer(run).data
            data["proposal_ids"] = getattr(run, "proposal_ids_out", None) or list(run.proposals.values_list("pk", flat=True))
            return Response(data, status=status.HTTP_200_OK)

        if spec.accepts_text:
            return wrap_idempotent(request=request, company=company, scope=SCOPE_RUN_START, build=build_from_text)

        def build():
            run = services.create_run(
                company=company, agent_kind=spec.kind, trigger=Trigger.ATTENTION_ROW if ser.validated_data["trigger_ref"] else Trigger.USER,
                trigger_ref=ser.validated_data["trigger_ref"], user=request.user,
            )
            from .tasks import run_agent_async

            run_agent_async.delay(run.pk, company_id=run.company_id)  # the worker needs the company to set its RLS context
            run.refresh_from_db()
            return Response(AgentRunSerializer(run).data, status=status.HTTP_202_ACCEPTED)

        return wrap_idempotent(request=request, company=company, scope=SCOPE_RUN_START, build=build)


class RunDetailView(AgentsBaseView):
    def get(self, request, pk):
        run = AgentRun.objects.filter(company=self.company, pk=pk).first()
        if run is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        cu = self.company_user
        if run.requested_by_id != request.user.pk and cu.role not in ("OWNER", "MANAGER"):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        data = AgentRunSerializer(run).data
        data["proposal_ids"] = list(run.proposals.values_list("pk", flat=True))
        return Response(data)


def _visible_kinds(company_user) -> list[str]:
    return [k for k, spec in PROPOSAL_KINDS.items() if policy.can_approve(company_user, spec)]


class ProposalListView(AgentsBaseView):
    def get(self, request):
        cu = self.company_user
        qs = AgentProposal.objects.filter(company=self.company, kind__in=_visible_kinds(cu)).select_related("run")
        statuses = request.query_params.get("status")
        qs = qs.filter(status__in=statuses.split(",")) if statuses else qs.filter(
            status__in=[ProposalStatus.PENDING, ProposalStatus.FAILED]
        )
        for param, field in (("kind", "kind"), ("dedupe_key", "dedupe_key"), ("group_key", "group_key")):
            if request.query_params.get(param):
                qs = qs.filter(**{field: request.query_params[param]})
        rows = AgentProposalSerializer(qs.order_by("-created_at")[:200], many=True, context=self._serializer_context()).data
        return Response({"results": rows, "count": len(rows)})


class ProposalDetailView(AgentsBaseView):
    def _get(self, pk):
        p = AgentProposal.objects.filter(company=self.company, pk=pk).select_related("run").first()
        if p is None or p.kind not in _visible_kinds(self.company_user):
            return None
        return p

    def get(self, request, pk):
        p = self._get(pk)
        if p is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(AgentProposalSerializer(p, context=self._serializer_context()).data)

    def patch(self, request, pk):
        if self._get(pk) is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        ser = EditProposalSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            p = services.edit_proposal(
                company=self.company, company_user=self.company_user, proposal_id=pk,
                edited_payload=ser.validated_data["edited_payload"], revision=ser.validated_data["revision"],
            )
        except BusinessRuleError as exc:
            raise self._forbidden(exc)
        return Response(AgentProposalSerializer(p, context=self._serializer_context()).data)


class _ProposalActionView(AgentsBaseView):
    def _visible(self, pk) -> bool:
        return AgentProposal.objects.filter(
            company=self.company, pk=pk, kind__in=_visible_kinds(self.company_user)
        ).exists()

    def _respond(self, p):
        return Response(AgentProposalSerializer(p, context=self._serializer_context()).data)


class ProposalApproveView(_ProposalActionView):
    def post(self, request, pk):
        if not self._visible(pk):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        ser = RevisionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        company, cu = self.company, self.company_user

        def build():
            try:
                p = services.approve_proposal(company=company, company_user=cu, proposal_id=pk, revision=ser.validated_data["revision"])
            except BusinessRuleError as exc:
                raise self._forbidden(exc)
            return self._respond(p)

        return wrap_idempotent(request=request, company=company, scope=SCOPE_APPROVE, build=build)


class ProposalRetryView(_ProposalActionView):
    def post(self, request, pk):
        if not self._visible(pk):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        ser = RevisionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        company, cu = self.company, self.company_user

        def build():
            try:
                p = services.retry_proposal(company=company, company_user=cu, proposal_id=pk, revision=ser.validated_data["revision"])
            except BusinessRuleError as exc:
                raise self._forbidden(exc)
            return self._respond(p)

        return wrap_idempotent(request=request, company=company, scope=SCOPE_APPROVE, build=build)


class ProposalRejectView(_ProposalActionView):
    def post(self, request, pk):
        if not self._visible(pk):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        ser = RejectSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            p = services.reject_proposal(company=self.company, company_user=self.company_user, proposal_id=pk, reason=ser.validated_data["reason"])
        except BusinessRuleError as exc:
            raise self._forbidden(exc)
        return self._respond(p)


class ProposalCancelView(_ProposalActionView):
    def post(self, request, pk):
        if not self._visible(pk):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            p = services.cancel_proposal(company=self.company, company_user=self.company_user, proposal_id=pk, note=str(request.data.get("note") or ""))
        except BusinessRuleError as exc:
            raise self._forbidden(exc)
        return self._respond(p)


class ProposalBulkApproveView(AgentsBaseView):
    """Reminders only (kinds with bulk_approvable). Each item is its own transaction."""

    def post(self, request):
        ser = BulkApproveSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        company, cu = self.company, self.company_user

        def build():
            results = []
            for item in ser.validated_data["items"]:
                pid, rev = item.get("id"), item.get("revision")
                p = AgentProposal.objects.filter(company=company, pk=pid).first()
                kind = PROPOSAL_KINDS.get(p.kind) if p else None
                if p is None or kind is None or not kind.bulk_approvable or not policy.can_approve(cu, kind):
                    results.append({"id": pid, "ok": False, "code": E.AGT_E_ROLE if p else "NOT_FOUND"})
                    continue
                try:
                    done = services.approve_proposal(company=company, company_user=cu, proposal_id=pid, revision=rev)
                    results.append({"id": pid, "ok": True, "status": done.status})
                except APIException as exc:
                    codes = exc.get_codes()
                    results.append({"id": pid, "ok": False, "code": codes if isinstance(codes, str) else "ERROR"})
            return Response({"results": results})

        return wrap_idempotent(request=request, company=company, scope=SCOPE_BULK_APPROVE, build=build)
