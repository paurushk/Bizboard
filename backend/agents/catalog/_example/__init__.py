"""Inert example agent used by the platform tests and as a copy-paste template (plan 13.4).

Autodiscover skips packages starting with an underscore, so this is only registered when a test does
``spec.register(AGENT)``.
"""

from __future__ import annotations

import json

from rest_framework import serializers

from agents import permissions, registry
from agents.executors import StaleProposal
from agents.spec import AgentSpec, ProposalKindSpec


class LookupArgs(serializers.Serializer):
    limit = serializers.IntegerField(required=False, min_value=1, max_value=50, default=5)


class NotePayloadV1(serializers.Serializer):
    text = serializers.CharField(max_length=2000)
    total = serializers.CharField(required=False, allow_blank=True, default="")
    fail: serializers.Field = serializers.CharField(required=False, allow_blank=True, default="")


if "example_lookup" not in registry.REGISTRY:

    @registry.tool(name="example_lookup", description="List example items.", args=LookupArgs, access=permissions.can_see_reports)
    def example_lookup(ctx, limit=5):
        return {"items": [{"id": i, "name": f"item-{i}"} for i in range(1, limit + 1)], "phone": "9876543210"}


def _execute(proposal, ctx):
    payload = proposal.effective_payload
    mode = payload.get("fail")
    if mode == "stale":
        raise StaleProposal()
    if mode == "rule":
        from core.exceptions import BusinessRuleError

        raise BusinessRuleError("Example business rule failed.", code="example_rule")
    if mode == "boom":
        raise RuntimeError("unexpected")
    return {"type": "example_note", "ref": ctx.external_ref, "date": ctx.today.isoformat()}


NOTE = ProposalKindSpec(
    kind="EXAMPLE_NOTE",
    payload_serializers={1: NotePayloadV1},
    executor=_execute,
    renderer="message",
    default_ttl_hours=24,
    bulk_approvable=True,
    approve_permission=permissions.owner_manager_accountant,
    title_key="agents.example.note",
)


def _context(tctx):
    return {"facts": {"count": 3, "total": "1500", "as_of": "ignored"}, "untrusted": {}}


def _rules_only(tctx, context):
    return [{
        "kind": "EXAMPLE_NOTE", "title": "Example note", "dedupe_key": f"example:{tctx.run.trigger_ref or tctx.run.pk}",
        "payload": {"text": "Rules draft for 3 items totalling 1500"},
        "evidence": [{"type": "fact", "id": "count", "label": "3 items", "fact": 3}],
    }]


def _parse(tctx, context, text):
    data = json.loads(text)
    return [{
        "kind": "EXAMPLE_NOTE", "title": "Example note", "dedupe_key": f"example:{tctx.run.trigger_ref or tctx.run.pk}",
        "payload": {"text": data["note"]},
        "evidence": [{"type": "fact", "id": "count", "label": "3 items", "fact": 3}],
    }]


def _validate(tctx, context, drafts):
    from agents import numbers
    from core.exceptions import BusinessRuleError

    for d in drafts:
        bad = numbers.invented_numbers(d["payload"]["text"], context["facts"], cited_count=3)
        if bad:
            raise BusinessRuleError(f"Draft contains numbers not in the facts: {bad}", code="AGT_E_VALIDATION")


AGENT = AgentSpec(
    kind="EXAMPLE",
    flag="AGENT_EXAMPLE",
    title_key="agents.example.title",
    proposal_kinds=[NOTE],
    tools=["example_lookup"],
    context_builder=_context,
    parse_final=_parse,
    validate=_validate,
    rules_only=_rules_only,
    prepare_permission=permissions.owner_manager_accountant,
    trigger_codes=["EXAMPLE_*", "AR_OVERDUE_CUSTOMER"],
    schedule={"hour": 8, "minute": 30},
    usage_feature_kind="EXAMPLE",
    package="_example",
)
