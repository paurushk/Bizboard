from rest_framework import serializers

from . import policy
from .models import AgentProposal, AgentRun
from .spec import PROPOSAL_KINDS


class AgentRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentRun
        fields = [
            "id", "agent", "trigger", "trigger_ref", "status", "error_code", "started_at", "finished_at",
            "step_count", "rules_only", "created_at",
        ]
        read_only_fields = fields


class AgentProposalSerializer(serializers.ModelSerializer):
    agent = serializers.CharField(source="run.agent", read_only=True)
    payload = serializers.SerializerMethodField()
    renderer = serializers.SerializerMethodField()
    can_approve = serializers.SerializerMethodField()
    bulk_approvable = serializers.SerializerMethodField()

    class Meta:
        model = AgentProposal
        fields = [
            "id", "agent", "kind", "status", "title", "payload", "schema_version", "revision", "evidence",
            "dedupe_key", "group_key", "expires_at", "attempts", "failure_code", "decision_note",
            "result_ref", "renderer", "can_approve", "bulk_approvable", "created_at",
        ]
        read_only_fields = fields

    def get_payload(self, obj):
        return obj.effective_payload

    def get_renderer(self, obj):
        kind = PROPOSAL_KINDS.get(obj.kind)
        return kind.renderer if kind else "unknown"

    def get_can_approve(self, obj):
        kind = PROPOSAL_KINDS.get(obj.kind)
        cu = self.context.get("company_user")
        return bool(kind and cu and policy.can_approve(cu, kind))

    def get_bulk_approvable(self, obj):
        kind = PROPOSAL_KINDS.get(obj.kind)
        return bool(kind and kind.bulk_approvable)


class StartRunSerializer(serializers.Serializer):
    agent = serializers.CharField(max_length=48)
    trigger_ref = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    # Only for agents whose spec sets accepts_text; the per-agent length cap is checked in the view.
    text = serializers.CharField(max_length=20000, required=False, allow_blank=True, default="")


class EditProposalSerializer(serializers.Serializer):
    edited_payload = serializers.DictField()
    revision = serializers.IntegerField(min_value=0)


class RevisionSerializer(serializers.Serializer):
    revision = serializers.IntegerField(min_value=0)


class RejectSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class BulkApproveSerializer(serializers.Serializer):
    items = serializers.ListField(
        child=serializers.DictField(), min_length=1, max_length=50,
    )
