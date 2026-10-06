"""Sales-order confirmation gates. Invoice and POS keep their own credit check."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.services.feature_flags import flag_enabled
from core.services.flag_observability import log_flag_event
from core.services.margin import MARGIN_THRESHOLD, margin_below_threshold, margin_ratio
from ledgers.services import LedgerService

OVERRIDE_REASON_MAX = 500


def sales_order_exposure(company, customer, order) -> Decimal:
    """Posted exposure plus other open orders and drafts, including this order.

    A confirmed order that already has a ledger-counted invoice contributes
    only the part the ledger has not picked up yet.
    """
    from sales.models import DeliveryChallan, SalesOrder
    from sales.status_semantics import OPEN_RECEIVABLE_STATUSES

    posted = LedgerService.customer_exposure_for_credit_limit(company, customer)
    others = list(
        SalesOrder.objects.filter(
            company=company,
            customer=customer,
            status__in=(SalesOrder.Status.DRAFT, SalesOrder.Status.CONFIRMED),
        )
        .exclude(pk=order.pk)
        .select_related("converted_invoice")
    )
    covered = _ledger_covered_by_order(company, others, OPEN_RECEIVABLE_STATUSES, DeliveryChallan)
    extra = Decimal("0")
    for row in others:
        remaining = (row.grand_total or Decimal("0")) - covered.get(row.pk, Decimal("0"))
        if remaining < 0:
            remaining = Decimal("0")
        extra += remaining
    return posted + extra + (order.grand_total or Decimal("0"))


def _ledger_invoice_value(invoice) -> Decimal:
    """The invoice figure `_customer_outstanding_documents` adds, before notes and receipts."""
    total = Decimal(str(invoice.grand_total or 0))
    if not getattr(invoice, "tcs_in_grand_total", True):
        total += Decimal(str(getattr(invoice, "tcs_amount", 0) or 0))
    return total


def _ledger_covered_by_order(company, orders, open_statuses, challan_model) -> dict[int, Decimal]:
    covered: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    seen: dict[int, set[int]] = defaultdict(set)

    def add(order_id, invoice):
        if invoice is None or invoice.status not in open_statuses:
            return
        if invoice.pk in seen[order_id]:
            return
        seen[order_id].add(invoice.pk)
        covered[order_id] += _ledger_invoice_value(invoice)

    order_ids = []
    for row in orders:
        order_ids.append(row.pk)
        add(row.pk, row.converted_invoice)
    if not order_ids:
        return covered
    challans = challan_model.objects.filter(
        company=company,
        sales_order_id__in=order_ids,
        converted_invoice__isnull=False,
    ).select_related("converted_invoice")
    for challan in challans:
        add(challan.sales_order_id, challan.converted_invoice)
    return covered


def company_allows_below_cost(company) -> bool:
    """Whether bills under purchase cost may complete without an owner's reason.

    A company setting decides, True or False. With nothing set, the process default applies
    (``settings.ALLOW_BELOW_COST_SALES_DEFAULT``, False in production: an owner records a reason).
    """
    from django.conf import settings

    for name in ("allow_below_cost_sales", "allow_below_cost"):
        value = getattr(company, name, None)
        if value is True or value is False:
            return value
    flags = getattr(company, "feature_flags", None) or {}
    if isinstance(flags, dict):
        for key in ("allow_below_cost_sales", "allow_below_cost", "ALLOW_BELOW_COST_SALES"):
            if flags.get(key) is True:
                return True
            if flags.get(key) is False:
                return False
    return bool(getattr(settings, "ALLOW_BELOW_COST_SALES_DEFAULT", False))


def _net_unit_price(item) -> Decimal:
    price = Decimal(str(getattr(item, "unit_price", 0) or 0))
    discount = Decimal(str(getattr(item, "discount_percent", 0) or 0))
    return price * (Decimal("1") - discount / Decimal("100"))


def below_cost_lines(items) -> list[str]:
    """Names of lines priced under purchase cost (net of the line discount)."""
    names = []
    for item in items:
        product = getattr(item, "product", None)
        if product is None:
            continue
        cost = Decimal(str(getattr(product, "purchase_price", 0) or 0))
        if cost <= 0:
            continue
        net = _net_unit_price(item)
        unit_name = getattr(item, "unit_name", None)
        if unit_name:
            # A price per box compared with a cost per piece would flag (or pass) the wrong sales:
            # bring the price to the base unit the cost is stated in.
            try:
                from inventory.item_stock import base_unit_cost

                net = base_unit_cost(product, net, unit_name)
            except Exception:  # noqa: BLE001 - an unreadable unit falls back to the stated price
                pass
        if net < cost:
            names.append(getattr(product, "name", "item"))
    return names


def assert_below_cost_blocked(company, items, *, override_reason: str = "", can_override: bool = False) -> list[str]:
    """Refuse to complete a bill priced under purchase cost.

    Allowed when the company opted in (``feature_flags.allow_below_cost_sales``) or when an
    owner/admin records a reason on this document. Returns the below-cost line names that
    were allowed through, so the caller can write them to the audit trail.
    """
    if company_allows_below_cost(company):
        return []
    names = below_cost_lines(items)
    if not names:
        return []
    if can_override and (override_reason or "").strip():
        return names
    raise BusinessRuleError(
        f"Cannot bill '{names[0]}' below purchase cost."
        + (" An owner can complete it with a reason." if len(names) else ""),
        code="below_cost",
    )


def margin_warnings(order, items) -> list[dict]:
    warnings = []
    for item in items:
        price = Decimal(str(item.unit_price or 0))
        cost = Decimal(str(getattr(item.product, "purchase_price", 0) or 0))
        if not margin_below_threshold(price, cost, MARGIN_THRESHOLD):
            continue
        ratio = margin_ratio(price, cost)
        warnings.append({
            "product_id": item.product_id,
            "product_name": item.product.name,
            "margin": str(ratio.quantize(Decimal("0.0001"))),
        })
    return warnings


def _owner_membership(company, acting_user, *, roles=None):
    """The acting user's CompanyUser membership, if it has one of ``roles``.

    Defaults to OWNER-only (the credit-limit override gate). GST Guard's
    override reuses this with ``roles=(OWNER, MANAGER)`` instead of
    duplicating the membership-resolution logic.
    """
    from accounts.models import CompanyUser

    if roles is None:
        roles = (CompanyUser.Role.OWNER,)
    if acting_user is None:
        return None
    if isinstance(acting_user, CompanyUser):
        if (
            acting_user.company_id == company.id
            and acting_user.role in roles
            and acting_user.user.is_active
        ):
            return acting_user
        return None
    return CompanyUser.objects.filter(
        company=company,
        user=acting_user,
        user__is_active=True,
        role__in=roles,
    ).first()


def apply_order_gates(order, items, *, override_reason=None, acting_user=None) -> list[dict]:
    """Hard-block credit unless an owner supplies a non-blank reason. Margin only warns."""
    from masters.models import Customer

    if not flag_enabled(order.company, "ENABLE_ORDER_GATES"):
        return []
    log_flag_event(order.company, "ENABLE_ORDER_GATES", "order_gate_checked", order_id=order.id)
    customer = Customer.objects.select_for_update().get(pk=order.customer_id)
    limit = Decimal(str(customer.credit_limit or 0))
    if limit > 0:
        exposure = sales_order_exposure(order.company, customer, order)
        if exposure > limit:
            # A non-string JSON value (int, dict, list) for override_reason
            # must not reach .strip() and crash with a 500 — treat it as no
            # reason, which correctly falls through to the hard block below.
            reason = override_reason.strip() if isinstance(override_reason, str) else ""
            owner = _owner_membership(order.company, acting_user)
            if not reason or len(reason) > OVERRIDE_REASON_MAX or owner is None:
                raise BusinessRuleError(
                    f"Credit limit exceeded. Exposure {exposure} > limit {limit}.",
                    code="credit_limit_exceeded",
                )
            order.credit_override_reason = reason
            order.credit_overridden_by = owner
            order.credit_overridden_at = timezone.now()
    warnings = margin_warnings(order, items)
    order._gate_warnings = warnings
    return warnings


def copy_credit_override(order, invoice) -> None:
    """Copy an order's override onto the invoice created from that order."""
    if order is None or invoice is None:
        return
    reason = (getattr(order, "credit_override_reason", "") or "").strip()
    if not reason or not order.credit_overridden_by_id or not order.credit_overridden_at:
        return
    invoice.credit_override_reason = reason
    invoice.credit_overridden_by_id = order.credit_overridden_by_id
    invoice.credit_overridden_at = order.credit_overridden_at
    invoice.save(update_fields=[
        "credit_override_reason", "credit_overridden_by", "credit_overridden_at", "updated_at",
    ])


def invoice_has_credit_override(invoice) -> bool:
    """True only when this invoice itself carries a copied override."""
    reason = (getattr(invoice, "credit_override_reason", "") or "").strip()
    return bool(reason and invoice.credit_overridden_by_id and invoice.credit_overridden_at)


def invoice_credit_override_covers(invoice) -> bool:
    """The copied override covers this invoice only up to the order total the owner approved."""
    if not invoice_has_credit_override(invoice):
        return False
    from sales.models import DeliveryChallan, SalesOrder

    order = SalesOrder.objects.filter(
        company_id=invoice.company_id, converted_invoice_id=invoice.pk,
    ).first()
    if order is None:
        challan = (
            DeliveryChallan.objects.filter(
                company_id=invoice.company_id, converted_invoice_id=invoice.pk,
            )
            .select_related("sales_order")
            .first()
        )
        order = challan.sales_order if challan is not None else None
    if order is None or not (getattr(order, "credit_override_reason", "") or "").strip():
        return False
    approved = Decimal(str(order.grand_total or 0))
    return Decimal(str(invoice.grand_total or 0)) <= approved + Decimal("0.01")
