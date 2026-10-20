from rest_framework import serializers

from .models import (
    AiUsageLedger,
    AssistantMessage,
    AssistantThread,
    BusinessAlertEvent,
    BusinessHealthSnapshot,
    CashflowForecastRun,
    DailyBusinessSummary,
)


class DailyBusinessSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyBusinessSummary
        fields = [
            "id", "summary_date", "kpis", "alert_codes", "narrative",
            "prompt_version", "email_sent_at", "created_at",
        ]


class BusinessAlertEventSerializer(serializers.ModelSerializer):
    snoozed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = BusinessAlertEvent
        fields = [
            "id", "code", "severity", "message", "subject_key", "payload",
            "status", "snoozed_until", "snoozed_at", "snoozed_by_name", "cta_path",
            "created_at", "updated_at",
        ]

    def get_snoozed_by_name(self, obj) -> str:
        user = obj.snoozed_by
        if user is None:
            return ""
        return (getattr(user, "get_full_name", lambda: "")() or user.get_username() or "").strip()

    def to_representation(self, instance):
        from django.utils import timezone

        data = super().to_representation(instance)
        # A snooze that has run out reads as open even before the nightly job reopens the row.
        if (
            instance.status == BusinessAlertEvent.Status.SNOOZED
            and instance.snoozed_until is not None
            and instance.snoozed_until <= timezone.now()
        ):
            data["status"] = BusinessAlertEvent.Status.OPEN
        return data


class BusinessHealthSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessHealthSnapshot
        fields = [
            "id", "as_of", "score", "grade", "factors", "limited_data", "created_at",
        ]


class CashflowForecastRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = CashflowForecastRun
        fields = [
            "id", "horizon_days", "mode", "series", "meta",
            "model_version", "inputs_hash", "created_at",
        ]


class AssistantMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssistantMessage
        fields = [
            "id", "role", "content", "tool_name", "citations",
            "proposed_action", "created_at",
        ]


class AssistantThreadSerializer(serializers.ModelSerializer):
    messages = AssistantMessageSerializer(many=True, read_only=True)

    class Meta:
        model = AssistantThread
        fields = ["id", "title", "created_at", "messages"]


class AssistantThreadListSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssistantThread
        fields = ["id", "title", "created_at"]


class AiUsageLedgerSerializer(serializers.ModelSerializer):
    class Meta:
        model = AiUsageLedger
        fields = [
            "id", "feature", "tokens_in", "tokens_out", "cost_estimate",
            "model_name", "prompt_version", "created_at",
        ]
