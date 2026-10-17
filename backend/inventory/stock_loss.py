"""One path for a stock change that is not a document (INV-IDR-02).

Manual adjustments, expiry write-offs, serial scrap and stock-count posting all move stock without a
sale, purchase or transfer behind them. They share the same controls, so they share this code:

* the closed-period gate,
* the second-person approval rule (``stock_adjustment_needs_second``),
* the movement itself, the optional journal (``ACCOUNTING_POST_STOCK_ADJUSTMENTS``) and the audit entry.

Approval rules
--------------
The manual adjustment always went through the approval rule. The other paths do so only when the
company has the ``STOCK_LOSS_APPROVAL_ALL_PATHS`` flag (off by default), and only for a loss.

An approval is a request the owner decides. Once approved it can be spent in two ways:

* a single-line request (adjustment, expiry write-off) is applied by the server the moment the owner
  approves it (``apply_approved_stock_loss``), so nobody has to come back and press Save again;
* every request can also be spent by the requester repeating the same action: the server finds the
  approved request for that exact subject, so the page does not have to carry an approval id.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.services.audit import AuditService
from core.services.feature_flags import flag_enabled

SOURCE_ADJUSTMENT = "manual_adjustment"
SOURCE_EXPIRY = "expiry_write_off"
SOURCE_SERIAL_SCRAP = "serial_scrap"
SOURCE_COUNT = "stock_count"
SOURCE_TRANSFER_SHORTAGE = "transfer_shortage"

# Sources the server can apply on its own once approved (one movement, nothing else to change).
SELF_APPLYING_SOURCES = frozenset({SOURCE_ADJUSTMENT, SOURCE_EXPIRY})

APPROVAL_FLAG = "STOCK_LOSS_APPROVAL_ALL_PATHS"


@dataclass
class StockLoss:
    """What is being written off, added back or corrected."""

    product: Any
    quantity: Decimal  # signed: negative takes stock out
    reason: str
    source: str
    warehouse: Any = None
    batch: Any = None
    reason_code: str = ""
    movement_date: date | None = None
    reference_id: Any = None
    # The adjustment screen warns / blocks on negative stock; the other paths never did.
    check_negative: bool = False
    skip_negative_check: bool = False
    check_period: bool = True
    audit_text: str = ""


@dataclass
class StockLossResult:
    status: str  # "APPLIED" | "PENDING"
    movement: Any = None
    approval: Any = None
    warnings: list[str] = field(default_factory=list)

    @property
    def pending(self) -> bool:
        return self.status == "PENDING"


def _resolved_warehouse(company, loss: StockLoss):
    from .services import InventoryService

    return loss.warehouse or InventoryService.default_warehouse(company)


def approval_subject(company, loss: StockLoss) -> dict:
    """The keys an approval is matched on. Same shape when it is raised and when it is spent."""
    warehouse = _resolved_warehouse(company, loss)
    subject = {
        "source": loss.source,
        "product": loss.product.pk,
        "quantity": str(loss.quantity),
        "warehouse": warehouse.pk if warehouse is not None else None,
        "batch": loss.batch.pk if loss.batch is not None else None,
    }
    if loss.reference_id not in (None, ""):
        subject["reference"] = str(loss.reference_id)
    return subject


def loss_value(company, loss: StockLoss) -> Decimal:
    """What the quantity is worth: the dearer of the item's purchase price and its valuation cost.

    The approval threshold used to read the purchase price alone, which is 0 for an item that was
    never priced; the valuation cost is what the stock is actually booked at.
    """
    from .services import InventoryValuationService

    quantity = abs(Decimal(str(loss.quantity)))
    price = Decimal(str(getattr(loss.product, "purchase_price", 0) or 0))
    try:
        cost = Decimal(str(
            InventoryValuationService.unit_cost(
                company, loss.product, warehouse=_resolved_warehouse(company, loss), batch=loss.batch,
            ) or 0
        ))
    except Exception:  # noqa: BLE001 - a cost that cannot be worked out must not stop the write
        cost = Decimal("0")
    return quantity * max(price, cost)


def needs_second_person(company, loss: StockLoss) -> bool:
    """True when this write must be approved by someone else before it posts."""
    from planwave.services import stock_adjustment_needs_second

    if loss.source != SOURCE_ADJUSTMENT:
        # Other paths: opt-in per company, and only a loss (found stock needs no approval here).
        if not flag_enabled(company, APPROVAL_FLAG) or loss.quantity >= 0:
            return False
    on_hand = _on_hand(company, loss)
    return stock_adjustment_needs_second(
        company, value=loss_value(company, loss), quantity=abs(loss.quantity), on_hand=on_hand,
    )


def _on_hand(company, loss: StockLoss) -> Decimal:
    from .models import StockBalance

    warehouse = _resolved_warehouse(company, loss)
    balance = StockBalance.objects.filter(company=company, product=loss.product, warehouse=warehouse).first()
    return Decimal(str(balance.on_hand or 0)) if balance is not None else Decimal("0")


def find_approved(company, user, subject: dict, approval_id=None):
    """Spend the approved request for this subject, if there is one. Returns the row or None."""
    from planwave.models import ApprovalRequest
    from planwave.services import consume_stock_approval

    if approval_id:
        row = consume_stock_approval(company, approval_id, user, **subject)
        if row is not None:
            return row
    candidates = ApprovalRequest.objects.filter(
        company=company, action="stock_adjustment", status=ApprovalRequest.Status.APPROVED,
        requester=user, token_used_at__isnull=True, expires_at__gt=timezone.now(),
    ).order_by("-id")[:20]
    for candidate in candidates:
        row = consume_stock_approval(company, candidate.pk, user, **subject)
        if row is not None:
            return row
    return None


def raise_for_approval(company, user, subject: dict, *, reason: str, apply: bool, approval_id=None):
    """Return (approval, pending): a spent approval to continue with, or a new pending request.

    A sole owner has nobody else to ask, so the request is raised and decided in one step (recorded
    as an owner exception) and the write continues.
    """
    from planwave.services import decide_approval, owner_is_sole_approver, submit_approval

    approval = find_approved(company, user, subject, approval_id)
    if approval is not None:
        return approval, False
    payload = dict(subject)
    payload["reason"] = reason
    payload["apply"] = bool(apply)
    pending = submit_approval(company=company, action="stock_adjustment", requester=user, payload=payload)
    if owner_is_sole_approver(company, user):
        pending.reason = "Owner is the only approver."
        pending.save(update_fields=["reason"])
        decide_approval(pending, approver=user, accept=True, owner_exception=True)
        return pending, False
    return pending, True


def post_stock_loss(company, user, loss: StockLoss, *, approval_id=None, preapproved: bool = False) -> StockLossResult:
    """Apply one stock loss (or gain) with every control. ``preapproved`` skips the approval check
    for a caller that has already decided it for a wider unit (a whole stock count)."""
    from reporting.gst_periods import assert_period_allows_money_amend

    from .models import MovementType
    from .services import InventoryService

    movement_date = loss.movement_date or timezone.localdate()
    if loss.check_period:
        assert_period_allows_money_amend(company, movement_date)

    approval = None
    if not preapproved and needs_second_person(company, loss):
        approval, pending = raise_for_approval(
            company, user, approval_subject(company, loss),
            reason=loss.reason, apply=loss.source in SELF_APPLYING_SOURCES, approval_id=approval_id,
        )
        if pending:
            return StockLossResult(status="PENDING", approval=approval)

    warnings: list[str] = []
    if loss.check_negative and loss.quantity < 0:
        warning = InventoryService.check_negative_stock(
            company, loss.product, -loss.quantity, loss.warehouse, batch=loss.batch,
        )
        if warning:
            warnings.append(warning)

    extra: dict[str, Any] = {}
    if loss.reference_id not in (None, ""):
        extra["reference_id"] = loss.reference_id
    if loss.reason_code:
        extra["reason_code"] = loss.reason_code
    if loss.movement_date is not None:
        extra["movement_date"] = loss.movement_date
    if loss.skip_negative_check:
        extra["skip_negative_check"] = True
    movement = InventoryService.post_movement(
        company=company,
        product=loss.product,
        movement_type=MovementType.ADJUSTMENT,
        quantity=loss.quantity,
        reason=loss.reason,
        reference_type=loss.source,
        user=user,
        warehouse=loss.warehouse,
        batch=loss.batch,
        **extra,
    )
    from accounting.services import PostingService

    PostingService.post_stock_adjustment(movement, user)
    if loss.audit_text:
        text = loss.audit_text
        if approval is not None:
            text = f"{text} (approval #{approval.pk})"
        AuditService.log(
            company=company, user=user, action="CREATE",
            entity_type="StockMovement", entity_id=movement.id, description=text,
        )
    return StockLossResult(status="APPLIED", movement=movement, approval=approval, warnings=warnings)


def apply_approved_stock_loss(approval) -> StockLossResult | None:
    """Apply an approved single-line request on the requester's behalf. None when it is not one."""
    from masters.models import Product

    from .models import BatchLot, Warehouse

    payload = approval.payload or {}
    source = payload.get("source")
    if source not in SELF_APPLYING_SOURCES or not payload.get("apply") or approval.requester is None:
        return None
    if approval.approver_id is None or approval.approver_id == approval.requester_id:
        # A self-approved request cannot be spent (the approval check refuses the same person).
        return None
    company = approval.company
    product = Product.objects.get(pk=payload["product"], company=company)
    warehouse = Warehouse.objects.filter(pk=payload.get("warehouse"), company=company).first()
    batch = BatchLot.objects.filter(pk=payload.get("batch"), company=company).first() if payload.get("batch") else None
    quantity = Decimal(str(payload["quantity"]))
    reason = str(payload.get("reason") or "")
    if source == SOURCE_EXPIRY:
        loss = StockLoss(
            product=product, quantity=quantity, reason=reason, source=source, warehouse=warehouse,
            batch=batch, skip_negative_check=True,
            audit_text=f"Write-off ({reason.lower()}): {abs(quantity)} of {product.name}, lot {getattr(batch, 'batch_no', '')}",
        )
    else:
        loss = StockLoss(
            product=product, quantity=quantity, reason=reason, source=source, warehouse=warehouse,
            batch=batch, check_negative=True, audit_text=f"Adjustment: {reason}",
        )
    return post_stock_loss(company, approval.requester, loss, approval_id=approval.pk)


def count_line_needs_recheck(line) -> bool:
    """A count difference big enough that the counter must look at it again before it posts."""
    from django.conf import settings

    variance = line.variance
    if variance is None or line.skipped or variance == 0:
        return False
    unit_limit = Decimal(str(getattr(settings, "STOCK_COUNT_AUTO_POST_QTY", "5")))
    value_limit = Decimal(str(getattr(settings, "STOCK_COUNT_RECHECK_VALUE", "10000")))
    price = Decimal(str(getattr(line.product, "purchase_price", 0) or 0))
    return abs(variance) > unit_limit or abs(variance * price) >= value_limit


def gate_count_post(company, user, session, planned, rechecked_ids, approval_id=None):
    """Checks a stock count must pass before it posts. ``planned`` is a list of
    ``(line, variance, current_qty)`` for the lines that will move stock.

    * Every line flagged for a second look must be named in ``rechecked_ids`` (server-enforced:
      raises ``recheck_required`` listing the ones missing).
    * With ``STOCK_LOSS_APPROVAL_ALL_PATHS`` on, the losses in the count are judged together (value,
      share of the counted stock) and individually; a count that needs a second person stays COUNTED
      until the owner approves it.

    Returns a pending ApprovalRequest, or None when the count may go ahead.
    """
    from planwave.services import stock_adjustment_needs_second

    needing = [line.pk for line, _variance, _current in planned if count_line_needs_recheck(line)]
    missing = [pk for pk in needing if pk not in rechecked_ids]
    if missing:
        raise BusinessRuleError(
            f"{len(missing)} line(s) with a large difference must be rechecked before posting.",
            code="recheck_required",
            extra={"line_ids": missing},
        )
    if not flag_enabled(company, APPROVAL_FLAG):
        return None
    losses = [(line, variance, current) for line, variance, current in planned if variance < 0]
    if not losses:
        return None
    total_value = Decimal("0")
    total_qty = Decimal("0")
    total_on_hand = Decimal("0")
    any_line = False
    for line, variance, current in losses:
        value = loss_value(
            company,
            StockLoss(
                product=line.product, quantity=variance, reason="STOCK_COUNT", source=SOURCE_COUNT,
                warehouse=session.warehouse, batch=line.batch,
            ),
        )
        total_value += value
        total_qty += abs(variance)
        total_on_hand += max(Decimal(str(current)), Decimal("0"))
        if stock_adjustment_needs_second(
            company, value=value, quantity=abs(variance), on_hand=Decimal(str(current)),
        ):
            any_line = True
    if not any_line and not stock_adjustment_needs_second(
        company, value=total_value, quantity=total_qty, on_hand=total_on_hand,
    ):
        return None
    approval, pending = raise_for_approval(
        company, user, {"source": SOURCE_COUNT, "session": session.pk},
        reason=f"Stock count #{session.pk} for {session.warehouse.name}", apply=False, approval_id=approval_id,
    )
    return approval if pending else None
