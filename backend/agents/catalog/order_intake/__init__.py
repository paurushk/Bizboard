"""Order Intake Agent (R3): reads a pasted customer order and drafts a Sales Order for a person to confirm.

L2: the draft is a proposal the person edits in the Quick Order grid and approves; approving creates a DRAFT
sales order (never a confirmed one, never an invoice). Corrections are learned as aliases so the same wording
needs no correction next time.
"""

from agents import permissions
from agents.executors.sales_order import execute_sales_order_draft
from agents.schemas.sales_order import SalesOrderDraftPayloadV1
from agents.spec import AgentSpec, ProposalKindSpec

from . import context

SALES_ORDER_DRAFT = ProposalKindSpec(
    kind="SALES_ORDER_DRAFT",
    payload_serializers={1: SalesOrderDraftPayloadV1},
    executor=execute_sales_order_draft,
    renderer="order",
    default_ttl_hours=48,
    bulk_approvable=False,
    approve_permission=permissions.can_create_sales,
    title_key="agents.orderIntake.draft",
)

AGENT = AgentSpec(
    kind="ORDER_INTAKE",
    flag="AGENT_ORDER_INTAKE",
    title_key="agents.orderIntake.title",
    proposal_kinds=[SALES_ORDER_DRAFT],
    tools=[],
    context_builder=context.build_context,
    parse_final=context.parse_final,
    validate=context.validate,
    rules_only=context.rules_only,
    prepare_permission=permissions.can_create_sales,
    usage_feature_kind="ORDER_INTAKE",
    limits={"per_company_daily_runs": 100, "run_timeout_s": 30},
    accepts_text=True,
    text_max_chars=6000,
)
