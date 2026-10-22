"""Inventory Risk Agent (R4): drafts the transfer and purchase documents the Purchase planning page would make.

L2: nothing moves and nothing is ordered until a person approves, and approving creates a DRAFT stock transfer or
a DRAFT purchase order only. Quantities are the existing planning rules' quantities; lot choice is earliest-expiry
among lots that are neither expired nor held by quality.
"""

from agents import permissions
from agents.executors.inventory import acknowledge_needs_supplier, execute_purchase, execute_transfer
from agents.schemas.inventory import NeedsSupplierPayloadV1, PurchasePayloadV1, TransferPayloadV1
from agents.spec import AgentSpec, ProposalKindSpec

from . import context

STOCK_TRANSFER = ProposalKindSpec(
    kind=context.TRANSFER,
    payload_serializers={1: TransferPayloadV1},
    executor=execute_transfer,
    renderer="lines",
    default_ttl_hours=48,
    approve_permission=permissions.can_manage_inventory,
    title_key="agents.inventory.transfer",
)
PURCHASE_REQUEST = ProposalKindSpec(
    kind=context.PURCHASE,
    payload_serializers={1: PurchasePayloadV1},
    executor=execute_purchase,
    renderer="lines",
    default_ttl_hours=48,
    approve_permission=permissions.can_create_purchases,
    title_key="agents.inventory.purchase",
)

NEEDS_SUPPLIER = ProposalKindSpec(
    kind=context.NEEDS_SUPPLIER,
    payload_serializers={1: NeedsSupplierPayloadV1},
    executor=acknowledge_needs_supplier,
    renderer="lines",
    default_ttl_hours=48,
    approve_permission=permissions.can_create_purchases,
    title_key="agents.inventory.needsSupplier",
)

AGENT = AgentSpec(
    kind="INVENTORY_RISK",
    flag="AGENT_INVENTORY_RISK",
    title_key="agents.inventory.title",
    proposal_kinds=[STOCK_TRANSFER, PURCHASE_REQUEST, NEEDS_SUPPLIER],
    tools=[],
    context_builder=context.build_context,
    parse_final=context.parse_final,
    validate=context.validate,
    rules_only=context.rules_only,
    prepare_permission=lambda cu: permissions.can_manage_inventory(cu) or permissions.can_create_purchases(cu),
    trigger_codes=["LOW_STOCK_FAST_MOVER"],
    schedule={"hour": 7, "minute": 30},
    usage_feature_kind="INVENTORY_RISK",
    limits={"per_company_daily_runs": 100},
    requires_flags=["ENABLE_PURCHASE_PLANNING", "ENABLE_REPLENISHMENT"],
    prompt_names=[],
)
