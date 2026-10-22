"""Collections Agent (R2): ranks who owes what and drafts reminders for a person to send.

L1: rows already exist in Needs attention. L2: a reminder draft (English or Hindi, polite or firm) with
the invoices it cites. Nothing is sent by the system; the user copies or shares the approved text.
"""

from agents import permissions
from agents.executors.reminder import execute_reminder
from agents.schemas.reminder import ReminderPayloadV1
from agents.spec import AgentSpec, ProposalKindSpec

from . import context

REMINDER = ProposalKindSpec(
    kind="REMINDER",
    payload_serializers={1: ReminderPayloadV1},
    executor=execute_reminder,
    renderer="message",
    default_ttl_hours=72,
    bulk_approvable=True,
    approve_permission=permissions.can_remind,
    title_key="agents.collections.reminder",
)

AGENT = AgentSpec(
    kind="COLLECTIONS",
    flag="AGENT_COLLECTIONS",
    title_key="agents.collections.title",
    proposal_kinds=[REMINDER],
    tools=[],
    context_builder=context.build_context,
    parse_final=context.parse_final,
    validate=context.validate,
    rules_only=context.rules_only,
    prepare_permission=permissions.can_remind,
    trigger_codes=["AR_CUSTOMER", "AR_COLLECTION_RISK", "AR_OVERDUE_*", "PROMISE_TO_PAY_DUE", "PREDICTED_LATE_PAYMENT"],
    schedule={"hour": 8, "minute": 30},
    usage_feature_kind="COLLECTIONS",
    limits={"per_company_daily_runs": 200, "sweep_top": context.SWEEP_TOP},
    still_open=context.still_open,
)
