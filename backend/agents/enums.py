"""Platform enums. Agent kinds and proposal kinds are NOT here: they come from specs (agents.spec)."""

from django.db import models


class RunStatus(models.TextChoices):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    CANCELLED = "CANCELLED"


LIVE_RUN_STATUSES = (RunStatus.QUEUED, RunStatus.RUNNING)


class Trigger(models.TextChoices):
    SCHEDULE = "SCHEDULE"
    ATTENTION_ROW = "ATTENTION_ROW"
    USER = "USER"
    EVENT = "EVENT"


class StepKind(models.TextChoices):
    MODEL = "MODEL"
    TOOL = "TOOL"
    POLICY_DENY = "POLICY_DENY"
    ERROR = "ERROR"


class Autonomy(models.IntegerChoices):
    """L1 read, L2 draft for approval, L3 bounded execution (only approved reminders, R6)."""

    L1 = 1
    L2 = 2
    L3 = 3


class ProposalStatus(models.TextChoices):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


LIVE_PROPOSAL_STATUSES = (ProposalStatus.PENDING, ProposalStatus.APPROVED)
TERMINAL_PROPOSAL_STATUSES = (
    ProposalStatus.EXECUTED,
    ProposalStatus.REJECTED,
    ProposalStatus.CANCELLED,
    ProposalStatus.EXPIRED,
)

# FAILED proposals with these codes cannot be reopened: the data changed, so re-prepare instead.
NON_RETRYABLE_FAILURES = frozenset({"STALE"})
MAX_EXECUTE_ATTEMPTS = 3

# Explicit transition table. Anything else is AGT_E_BAD_TRANSITION.
ALLOWED_TRANSITIONS = {
    ProposalStatus.PENDING: {
        ProposalStatus.APPROVED,
        ProposalStatus.REJECTED,
        ProposalStatus.CANCELLED,
        ProposalStatus.EXPIRED,
    },
    ProposalStatus.APPROVED: {ProposalStatus.EXECUTED, ProposalStatus.FAILED},
    ProposalStatus.FAILED: {ProposalStatus.PENDING, ProposalStatus.CANCELLED},
    ProposalStatus.EXECUTED: set(),
    ProposalStatus.REJECTED: set(),
    ProposalStatus.CANCELLED: set(),
    ProposalStatus.EXPIRED: set(),
}
