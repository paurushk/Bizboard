"""Agent runs, steps, proposals and learned aliases. All tenant-scoped and enrolled in RLS.

`agent` and `kind` are plain CharFields with no DB choices: they are validated against the
spec registry (agents.spec) so adding an agent never needs a migration.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q

from core.exceptions import BusinessRuleError
from core.models import CompanyScopedModel, TimeStampedModel

from .enums import (
    LIVE_PROPOSAL_STATUSES,
    LIVE_RUN_STATUSES,
    Autonomy,
    ProposalStatus,
    RunStatus,
    StepKind,
    Trigger,
)


class AgentRun(CompanyScopedModel):
    agent = models.CharField(max_length=48)
    trigger = models.CharField(max_length=16, choices=Trigger.choices, default=Trigger.USER)
    trigger_ref = models.CharField(max_length=255, blank=True, default="")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    status = models.CharField(max_length=20, choices=RunStatus.choices, default=RunStatus.QUEUED)
    error_code = models.CharField(max_length=40, blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    step_count = models.PositiveSmallIntegerField(default=0)
    tokens_in = models.PositiveIntegerField(default=0)
    tokens_out = models.PositiveIntegerField(default=0)
    model_name = models.CharField(max_length=64, blank=True, default="")
    prompt_version = models.CharField(max_length=32, blank=True, default="")
    input_digest = models.CharField(max_length=64, blank=True, default="")
    rules_only = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["company", "agent", "created_at"])]
        constraints = [
            # One live run per (company, agent, trigger_ref): blocks duplicate concurrent runs.
            models.UniqueConstraint(
                fields=["company", "agent", "trigger_ref"],
                condition=Q(status__in=[s.value for s in LIVE_RUN_STATUSES]) & ~Q(trigger_ref=""),
                name="agents_run_one_live_per_ref",
            )
        ]

    def __str__(self) -> str:
        return f"{self.agent} run {self.pk} ({self.status})"


class AgentStep(CompanyScopedModel):
    """One model turn or tool call. Carries its own company_id so RLS applies directly."""

    run = models.ForeignKey(AgentRun, on_delete=models.CASCADE, related_name="steps")
    seq = models.PositiveSmallIntegerField()
    kind = models.CharField(max_length=16, choices=StepKind.choices)
    tool_name = models.CharField(max_length=64, blank=True, default="")
    args = models.JSONField(default=dict, blank=True)
    result_summary = models.JSONField(default=dict, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)
    tokens_in = models.PositiveIntegerField(default=0)
    tokens_out = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["run_id", "seq"]
        indexes = [models.Index(fields=["company", "run", "seq"])]
        constraints = [models.UniqueConstraint(fields=["run", "seq"], name="agents_step_unique_seq")]

    def save(self, *args, **kwargs):
        if self.run_id and self.company_id and self.run.company_id != self.company_id:
            raise BusinessRuleError("Agent step company must match its run.")
        super().save(*args, **kwargs)


class AgentProposal(CompanyScopedModel):
    run = models.ForeignKey(AgentRun, on_delete=models.PROTECT, related_name="proposals")
    kind = models.CharField(max_length=48)
    autonomy = models.PositiveSmallIntegerField(choices=Autonomy.choices, default=Autonomy.L2)
    status = models.CharField(max_length=16, choices=ProposalStatus.choices, default=ProposalStatus.PENDING)
    title = models.CharField(max_length=160)
    payload = models.JSONField(default=dict)
    schema_version = models.PositiveSmallIntegerField(default=1)
    revision = models.PositiveSmallIntegerField(default=0)
    evidence = models.JSONField(default=list)
    dedupe_key = models.CharField(max_length=255)
    group_key = models.CharField(max_length=255, blank=True, default="")
    expires_at = models.DateTimeField()
    assignee = models.ForeignKey(
        "accounts.CompanyUser", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=500, blank=True, default="")
    idempotency_key = models.CharField(max_length=64)
    attempts = models.PositiveSmallIntegerField(default=0)
    result_ref = models.JSONField(null=True, blank=True)
    failure_code = models.CharField(max_length=40, blank=True, default="")
    edited_payload = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["company", "status", "expires_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "kind", "dedupe_key"],
                condition=Q(status__in=[s.value for s in LIVE_PROPOSAL_STATUSES]),
                name="agents_proposal_one_live_per_key",
            )
        ]

    def __str__(self) -> str:
        return f"{self.kind} proposal {self.pk} ({self.status})"

    @property
    def effective_payload(self) -> dict:
        return self.edited_payload if self.edited_payload is not None else self.payload


class AgentAlias(CompanyScopedModel):
    """Learned text -> master mapping (R3). Exactly one of customer / product is set."""

    SCOPE_CUSTOMER = "CUSTOMER"
    SCOPE_PRODUCT = "PRODUCT"
    SCOPES = [(SCOPE_CUSTOMER, "Customer"), (SCOPE_PRODUCT, "Product")]

    scope = models.CharField(max_length=10, choices=SCOPES)
    raw_text_norm = models.CharField(max_length=255)
    customer = models.ForeignKey("masters.Customer", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    product = models.ForeignKey("masters.Product", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    hits = models.PositiveIntegerField(default=1)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "scope", "raw_text_norm"], name="agents_alias_unique"),
            models.CheckConstraint(
                condition=(
                    (Q(scope="CUSTOMER") & Q(customer__isnull=False) & Q(product__isnull=True))
                    | (Q(scope="PRODUCT") & Q(product__isnull=False) & Q(customer__isnull=True))
                ),
                name="agents_alias_exactly_one_target",
            ),
        ]


__all__ = ["AgentRun", "AgentStep", "AgentProposal", "AgentAlias", "TimeStampedModel"]
