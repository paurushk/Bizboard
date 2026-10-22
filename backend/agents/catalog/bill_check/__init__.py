"""Bill Check Agent (R5): compares draft purchase bills with their order and goods receipt and drafts a query to
the supplier. L2: the person edits the message, then copies or shares it. The agent never blocks, edits or completes
a bill; the existing 3-way match on Complete is unchanged.
"""

from agents import permissions
from agents.executors.supplier_query import acknowledge_bill_note, execute_supplier_query
from agents.schemas.bill_check import BillReviewNotePayloadV1, SupplierQueryPayloadV1
from agents.spec import AgentSpec, ProposalKindSpec

from . import context

SUPPLIER_QUERY = ProposalKindSpec(
    kind=context.KIND,
    payload_serializers={1: SupplierQueryPayloadV1},
    executor=execute_supplier_query,
    renderer="comparison",
    default_ttl_hours=72,
    approve_permission=permissions.can_create_purchases,
    title_key="agents.billCheck.query",
)

BILL_REVIEW_NOTE = ProposalKindSpec(
    kind=context.NOTE_KIND,
    payload_serializers={1: BillReviewNotePayloadV1},
    executor=acknowledge_bill_note,
    renderer="comparison",
    default_ttl_hours=72,
    approve_permission=permissions.can_create_purchases,
    title_key="agents.billCheck.note",
)

AGENT = AgentSpec(
    kind="BILL_CHECK",
    flag="AGENT_BILL_CHECK",
    title_key="agents.billCheck.title",
    proposal_kinds=[SUPPLIER_QUERY, BILL_REVIEW_NOTE],
    tools=[],
    context_builder=context.build_context,
    parse_final=context.parse_final,
    validate=context.validate,
    rules_only=context.rules_only,
    prepare_permission=permissions.can_create_purchases,
    schedule={"hour": 9, "minute": 0},
    usage_feature_kind="BILL_CHECK",
    limits={"per_company_daily_runs": 200},
    still_open=context.still_open,
)
