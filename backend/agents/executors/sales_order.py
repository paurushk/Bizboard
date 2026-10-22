"""SALES_ORDER_DRAFT executor (R3): creates a DRAFT SalesOrder the same way a hand-entered one is made.

Reuses SalesNotesService.set_order_items, so pricing (price list, scheme), GST and totals are the existing
rules; the agent supplies only product ids and quantities. Runs inside the approve transaction, so the order,
the learned aliases and the EXECUTED status commit together or not at all. The date is the day of approval.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.exceptions import BusinessRuleError

from .. import error_codes as E
from . import ExecContext, StaleProposal


def _line_source(original: list[dict], index: int, line: dict) -> str:
    """How this line was matched, treating a product the person changed as a manual pick."""
    source = (line.get("match") or {}).get("source", "none")
    if index < len(original) and original[index].get("raw") == line.get("raw") and original[index].get("product_id") != line.get("product_id"):
        return "manual"
    return source


def _learn(company, user, scope: str, norm: str, *, customer=None, product=None) -> None:
    from agents.models import AgentAlias

    if not norm:
        return
    now = timezone.now()
    alias = AgentAlias.objects.select_for_update().filter(company=company, scope=scope, raw_text_norm=norm).first()
    if alias is None:
        try:
            with transaction.atomic():  # a savepoint: losing the race must not abort the order's transaction
                AgentAlias.objects.create(
                    company=company, scope=scope, raw_text_norm=norm, customer=customer, product=product, hits=1,
                    last_used_at=now, created_by=user, updated_by=user,
                )
            return
        except IntegrityError:
            alias = AgentAlias.objects.select_for_update().get(company=company, scope=scope, raw_text_norm=norm)
    same = (alias.customer_id == getattr(customer, "pk", None)) if scope == AgentAlias.SCOPE_CUSTOMER else (alias.product_id == getattr(product, "pk", None))
    if same:
        alias.hits += 1
    else:
        alias.customer, alias.product, alias.hits = customer, product, 1  # the person corrected an earlier guess
    alias.last_used_at, alias.updated_by = now, user
    alias.save()


def execute_sales_order_draft(proposal, ctx: ExecContext) -> dict:
    from agents.models import AgentAlias
    from masters.models import Customer, Product
    from sales.models import SalesOrder
    from sales.notes_services import SalesNotesService, _single_active_company_gstin
    from sales.phase1_serializers import SalesOrderSerializer

    company, user = ctx.company, ctx.company_user.user
    payload, original = proposal.effective_payload, proposal.payload
    customer = Customer.objects.filter(company=company, pk=payload.get("customer_id")).first()
    if customer is None:
        raise BusinessRuleError("Pick the customer before approving.", code=E.AGT_E_VALIDATION)
    if customer.status != Customer.Status.ACTIVE:
        raise BusinessRuleError(f"Cannot create an order for {customer.billing_block_phrase}.", code=E.AGT_E_VALIDATION)

    rows = payload.get("lines") or []
    missing = [i + 1 for i, l in enumerate(rows) if not l.get("product_id") or not l.get("qty")]
    if missing:
        raise BusinessRuleError(f"Pick a product and quantity for line {', '.join(map(str, missing))}.", code=E.AGT_E_VALIDATION)
    products = {p.pk: p for p in Product.objects.filter(company=company, pk__in={l["product_id"] for l in rows})}
    if len(products) != len({l["product_id"] for l in rows}):
        raise StaleProposal("A product on this draft no longer exists.")
    inactive = [p.name for p in products.values() if p.status != Product.Status.ACTIVE]
    if inactive:
        raise StaleProposal(f"{inactive[0]} is no longer active.")

    order = SalesOrder.objects.create(
        company=company, customer=customer, order_date=ctx.today, payment_terms_days=customer.credit_days or 0,
        delivery_address=SalesOrderSerializer._default_delivery_address(customer, None),
        company_gstin=_single_active_company_gstin(company),
        notes=(f"Created from an agent draft (#{proposal.pk}). {payload.get('notes') or ''}").strip()[:2000],
        created_by=user, updated_by=user,
    )
    SalesNotesService.set_order_items(
        order, [{"product": products[l["product_id"]], "quantity": Decimal(l["qty"])} for l in rows], user,
    )

    original_lines = original.get("lines") or []
    for i, line in enumerate(rows):
        if _line_source(original_lines, i, line) not in ("code", "name"):
            _learn(company, user, AgentAlias.SCOPE_PRODUCT, line.get("raw_norm", ""), product=products[line["product_id"]])
    from agents.catalog.order_intake.parsing import normalize

    cust_source = (payload.get("customer_match") or {}).get("source", "none")
    if original.get("customer_id") != payload.get("customer_id"):
        cust_source = "manual"
    if cust_source not in ("name", "phone"):
        _learn(company, user, AgentAlias.SCOPE_CUSTOMER, normalize(payload.get("customer_hint", "")), customer=customer)

    return {
        "type": "sales_order", "id": order.pk, "number": order.number, "status": order.status,
        "lines": len(rows), "ref": ctx.external_ref, "date": ctx.today.isoformat(),
    }
