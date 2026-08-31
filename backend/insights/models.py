from django.conf import settings
from django.db import models

from core.models import CompanyScopedModel, TimeStampedModel


class DailyBusinessSummary(CompanyScopedModel):
    """Idempotent daily KPI + alert snapshot per company."""

    summary_date = models.DateField()
    kpis = models.JSONField(default=dict, blank=True)
    alert_codes = models.JSONField(default=list, blank=True)
    narrative = models.TextField(blank=True)
    prompt_version = models.CharField(max_length=32, blank=True, default="")
    email_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("company", "summary_date")]
        ordering = ["-summary_date"]
        indexes = [models.Index(fields=["company", "summary_date"])]


class AttentionRowState(CompanyScopedModel):
    """B-05: per-row snooze / first-seen for the frozen AttentionRow contract."""

    dedupe_key = models.CharField(max_length=191, db_index=True)
    first_seen = models.DateTimeField()
    snooze_until = models.DateTimeField(null=True, blank=True)
    snooze_reason = models.TextField(blank=True, default="")
    dismissed = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "dedupe_key"],
                name="uniq_attention_row_state_per_company",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "snooze_until"]),
        ]


class BusinessAlertEvent(CompanyScopedModel):
    class Severity(models.TextChoices):
        CRITICAL = "critical"
        WARNING = "warning"
        INFO = "info"

    class Status(models.TextChoices):
        OPEN = "OPEN"
        SNOOZED = "SNOOZED"
        RESOLVED = "RESOLVED"

    code = models.CharField(max_length=64, db_index=True)
    severity = models.CharField(max_length=16, choices=Severity.choices)
    message = models.TextField()
    subject_key = models.CharField(max_length=128, blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    snoozed_until = models.DateTimeField(null=True, blank=True)
    cta_path = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "status", "severity"]),
            models.Index(fields=["company", "code", "subject_key"]),
        ]


class BusinessHealthSnapshot(CompanyScopedModel):
    as_of = models.DateField()
    score = models.DecimalField(max_digits=5, decimal_places=2)
    grade = models.CharField(max_length=1)
    factors = models.JSONField(default=list, blank=True)
    limited_data = models.BooleanField(default=False)

    class Meta:
        unique_together = [("company", "as_of")]
        ordering = ["-as_of"]


class CashflowForecastRun(CompanyScopedModel):
    horizon_days = models.PositiveSmallIntegerField()
    mode = models.CharField(max_length=16, default="relative")  # relative | absolute
    series = models.JSONField(default=list, blank=True)
    meta = models.JSONField(default=dict, blank=True)
    model_version = models.CharField(max_length=32, default="v1")
    inputs_hash = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]


class AssistantThread(CompanyScopedModel):
    title = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        ordering = ["-created_at"]


class AssistantMessage(TimeStampedModel):
    class Role(models.TextChoices):
        USER = "user"
        ASSISTANT = "assistant"
        SYSTEM = "system"
        TOOL = "tool"

    thread = models.ForeignKey(AssistantThread, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=16, choices=Role.choices)
    content = models.TextField(blank=True, default="")
    tool_name = models.CharField(max_length=64, blank=True, default="")
    citations = models.JSONField(default=list, blank=True)
    proposed_action = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]


class AiUsageLedger(CompanyScopedModel):
    class Feature(models.TextChoices):
        EXTRACT = "EXTRACT"
        ASSISTANT = "ASSISTANT"
        SUMMARY_NARRATIVE = "SUMMARY_NARRATIVE"

    feature = models.CharField(max_length=32, choices=Feature.choices)
    tokens_in = models.PositiveIntegerField(default=0)
    tokens_out = models.PositiveIntegerField(default=0)
    cost_estimate = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    model_name = models.CharField(max_length=64, blank=True, default="")
    prompt_version = models.CharField(max_length=32, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["company", "feature", "created_at"])]


class ShopFloorEvent(CompanyScopedModel):
    """A-08: first-party shop-floor telemetry. No PII in event or props."""

    class Event(models.TextChoices):
        INVOICE_COMPLETE = "invoice_complete"
        POS_LINE_ADDED = "pos_line_added"
        OFFLINE_ENQUEUE = "offline_enqueue"
        OFFLINE_FLUSH_FAIL = "offline_flush_fail"
        COMPLETE_DURATION_MS = "complete_duration_ms"
        TIME_TO_FIRST_INVOICE_MS = "time_to_first_invoice_ms"

    event = models.CharField(max_length=40, choices=Event.choices, db_index=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    tap_count = models.PositiveSmallIntegerField(null=True, blank=True)
    occurred_on = models.DateField(db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["company", "event", "occurred_on"])]
