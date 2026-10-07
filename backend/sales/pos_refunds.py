"""Counter refunds: Dr 2300 / Cr cash or the mapped bank. The credit note is untouched."""

from __future__ import annotations

import hashlib
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Sum
from django.utils import timezone

from core.exceptions import BusinessRuleError

Q2 = Decimal("0.01")


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Q2, rounding=ROUND_HALF_UP)


def peeled_amount(sales_return) -> Decimal:
    from sales.models import SalesCreditNote

    total = Decimal("0")
    notes = SalesCreditNote.objects.filter(
        sales_return=sales_return,
        status=SalesCreditNote.Status.COMPLETED,
    )
    for note in notes:
        for sliver in note.peeled_receipt_allocations or []:
            total += _money((sliver or {}).get("amount"))
    return total.quantize(Q2, rounding=ROUND_HALF_UP)


def refund_room(sales_return) -> Decimal:
    """What this return may still hand back: peeled amount minus refunds already posted, and the 2300 balance."""
    from ledgers.services import LedgerService
    from sales.models import PosCounterRefund

    peeled = peeled_amount(sales_return)
    already = PosCounterRefund.objects.filter(
        sales_return=sales_return,
        status__in=(
            PosCounterRefund.Status.POSTED,
            PosCounterRefund.Status.PENDING_GATEWAY,
        ),
        mode__in=(PosCounterRefund.Mode.CASH, PosCounterRefund.Mode.BANK),
    ).aggregate(s=Sum("amount"))["s"]
    left = peeled - _money(already)
    if left < 0:
        left = Decimal("0")
    advance = LedgerService.customer_unallocated_receipts(sales_return.company, sales_return.customer)
    return min(left, _money(advance)).quantize(Q2, rounding=ROUND_HALF_UP)


def _peeled_receipts(sales_return):
    from payments.models import CustomerReceipt
    from sales.models import SalesCreditNote

    ids = []
    notes = SalesCreditNote.objects.filter(
        sales_return=sales_return,
        status=SalesCreditNote.Status.COMPLETED,
    )
    for note in notes:
        for sliver in note.peeled_receipt_allocations or []:
            raw = (sliver or {}).get("receipt_id")
            if raw:
                ids.append(raw)
    if not ids:
        return []
    return list(CustomerReceipt.objects.filter(company=sales_return.company, pk__in=ids))


def default_refund_mode(sales_return) -> str:
    from sales.models import PosCounterRefund

    receipts = _peeled_receipts(sales_return)
    if receipts and all(str(row.mode).upper() == "CASH" for row in receipts):
        return PosCounterRefund.Mode.CASH
    if receipts:
        return PosCounterRefund.Mode.BANK
    return PosCounterRefund.Mode.ADVANCE


def refund_key_prefix(raw: str) -> str:
    """Bound a client key so a shorter key cannot replay a longer one.

    Stored rows use ``{length}:{key}:{index}``. A key that would not fit the
    64-character column is stored by its length and a hash of the full key.
    """
    raw = str(raw or "").strip()
    if not raw:
        return ""
    plain = f"{len(raw)}:{raw}:"
    if len(plain) <= 61:
        return plain
    digest = hashlib.sha256(raw.encode()).hexdigest()[:32]
    return f"{len(raw)}:{digest}:"


def refund_row_key(raw: str, index: int) -> str:
    prefix = refund_key_prefix(raw)
    if not prefix:
        return ""
    return f"{prefix}{index}"[:64]


def _bank_account_for_refund(receipts):
    """The bank on a non-cash peeled receipt. Cash is never a stand-in."""
    for row in receipts:
        if str(row.mode).upper() != "CASH" and getattr(row, "bank_account_id", None):
            return row.bank_account
    return None


def stage_refunds(sales_return, parts, *, user, shift=None, idempotency_key: str = "") -> tuple[list, list]:
    """Create refund rows inside the caller's transaction.

    Returns (rows, gateway_calls). Gateway calls must run after the transaction commits.
    """
    from accounting.services import PostingService
    from sales.models import PosCounterRefund

    if not parts:
        return [], []
    key = str(idempotency_key or "").strip()
    if key:
        existing = list(
            PosCounterRefund.objects.filter(
                company=sales_return.company,
                sales_return=sales_return,
                idempotency_key__startswith=refund_key_prefix(key),
            )
        )
        if existing:
            return existing, []
    customer = sales_return.customer
    rows = []
    gateway_calls = []
    receipts = _peeled_receipts(sales_return)
    non_cash = [row for row in receipts if str(row.mode).upper() != "CASH"]
    gateway = [row for row in non_cash if getattr(row, "gateway_payment_id", None)]
    for index, part in enumerate(parts):
        mode = str((part or {}).get("mode") or default_refund_mode(sales_return)).upper()
        if mode not in (PosCounterRefund.Mode.CASH, PosCounterRefund.Mode.BANK, PosCounterRefund.Mode.ADVANCE):
            raise BusinessRuleError(f"Unknown refund mode '{mode}'.", code="pos_refund_mode")
        if mode == PosCounterRefund.Mode.ADVANCE and getattr(customer, "is_pos_walk_in", False):
            raise BusinessRuleError(
                "A walk-in return must be refunded in cash or to the bank.",
                code="pos_refund_walk_in",
            )
        row_key = refund_row_key(key, index)
        if mode == PosCounterRefund.Mode.ADVANCE:
            rows.append(PosCounterRefund.objects.create(
                company=sales_return.company,
                customer=customer,
                sales_return=sales_return,
                amount=Decimal("0.00"),
                mode=mode,
                status=PosCounterRefund.Status.ADVANCE,
                cashier=user,
                refund_date=timezone.localdate(),
                idempotency_key=row_key,
                shift=shift,
                created_by=user,
                updated_by=user,
            ))
            continue
        room = refund_room(sales_return)
        raw = (part or {}).get("amount")
        amount = room if raw in (None, "") else _money(raw)
        if amount <= 0:
            raise BusinessRuleError("Nothing was paid on this bill to hand back.", code="pos_refund_empty")
        if amount > room:
            raise BusinessRuleError(
                f"Refund {amount} is above the {room} this return peeled into advances.",
                code="pos_refund_cap",
            )
        # One provider payment only: a refund split across several would need
        # per-payment amounts, so those go to the mapped bank by hand instead.
        use_gateway = (
            mode == PosCounterRefund.Mode.BANK and len(gateway) == 1 and len(gateway) == len(non_cash)
        )
        row = PosCounterRefund.objects.create(
            company=sales_return.company,
            customer=customer,
            sales_return=sales_return,
            amount=amount,
            mode=mode,
            status=(
                PosCounterRefund.Status.PENDING_GATEWAY
                if use_gateway
                else PosCounterRefund.Status.POSTED
            ),
            cashier=user,
            refund_date=timezone.localdate(),
            bank_account=_bank_account_for_refund(receipts) if mode == PosCounterRefund.Mode.BANK else None,
            idempotency_key=row_key,
            shift=shift,
            created_by=user,
            updated_by=user,
        )
        if use_gateway:
            gateway_calls.append((gateway[0].gateway_payment, amount, row))
        else:
            if mode == PosCounterRefund.Mode.BANK and row.bank_account_id is None:
                raise BusinessRuleError(
                    "This bill has no bank account to refund to.",
                    code="pos_refund_bank",
                )
            _post_refund_journal(row, user, PostingService)
        rows.append(row)
    return rows, gateway_calls


def _post_refund_journal(row, user, PostingService) -> None:
    company = row.company
    if not getattr(company, "accounting_enabled", False):
        return
    PostingService._ensure_chart(company)
    if row.mode == row.Mode.BANK:
        if row.bank_account_id is None:
            raise BusinessRuleError(
                "This bill has no bank account to refund to.",
                code="pos_refund_bank",
            )
        credit = PostingService._bank_gl_account(company, row.bank_account, row.refund_date)
    else:
        credit = PostingService._account(company, "1100")
    PostingService.post(
        company=company,
        source_type="POS_REFUND",
        source_id=row.id,
        purpose="REFUND",
        entry_date=row.refund_date,
        user=user,
        narration=f"Counter refund {row.sales_return.number}",
        lines=[
            {"account": PostingService._account(company, "2300"), "debit": row.amount, "customer": row.customer},
            {"account": credit, "credit": row.amount},
        ],
    )


def finish_gateway_refunds(gateway_calls, user) -> None:
    """Provider refunds run outside the return's transaction."""
    from payments.services import PaymentService

    for gateway_payment, amount, row in gateway_calls:
        PaymentService.refund_gateway_payment(
            gateway_payment=gateway_payment,
            amount=amount,
            user=user,
            reason=f"Counter return {row.sales_return_id}",
            refund_key_override=row.idempotency_key or f"pos-refund-{row.pk}",
        )
        row.status = row.Status.POSTED
        row.save(update_fields=["status", "updated_at"])


def retry_pending_gateway_refunds(rows, user) -> None:
    """A replay after the provider call failed should finish the same refund, not skip it."""
    pending = [row for row in rows if row.status == row.Status.PENDING_GATEWAY]
    calls = []
    for row in pending:
        receipts = _peeled_receipts(row.sales_return)
        gateway = next((item for item in receipts if getattr(item, "gateway_payment_id", None)), None)
        if gateway is None:
            continue
        calls.append((gateway.gateway_payment, row.amount, row))
    if calls:
        finish_gateway_refunds(calls, user)


def proportional_refund_parts(sales_return) -> list[dict]:
    """Split the peeled amount across cash and bank in the original proportions."""
    from payments.models import CustomerReceipt
    from sales.models import SalesCreditNote

    buckets = {"CASH": Decimal("0"), "BANK": Decimal("0")}
    notes = SalesCreditNote.objects.filter(
        sales_return=sales_return,
        status=SalesCreditNote.Status.COMPLETED,
    )
    for note in notes:
        for sliver in note.peeled_receipt_allocations or []:
            amount = _money((sliver or {}).get("amount"))
            receipt = CustomerReceipt.objects.filter(
                company=sales_return.company, pk=(sliver or {}).get("receipt_id"),
            ).first()
            mode = "CASH" if receipt is not None and str(receipt.mode).upper() == "CASH" else "BANK"
            buckets[mode] += amount
    total = buckets["CASH"] + buckets["BANK"]
    room = refund_room(sales_return)
    if total <= 0 or room <= 0:
        raise BusinessRuleError("Nothing was paid on this bill to hand back.", code="pos_refund_empty")
    parts = []
    remaining = room
    modes = [mode for mode in ("CASH", "BANK") if buckets[mode] > 0]
    for index, mode in enumerate(modes):
        if index == len(modes) - 1:
            share = remaining
        else:
            share = min(
                (room * buckets[mode] / total).quantize(Q2, rounding=ROUND_HALF_UP),
                remaining,
            )
            remaining -= share
        if share > 0:
            parts.append({"mode": mode, "amount": share})
    if not parts:
        raise BusinessRuleError("Nothing was paid on this bill to hand back.", code="pos_refund_empty")
    return parts


def parse_refund_parts(data) -> list[dict] | None:
    """None means the caller did not ask for a refund (leave the advance)."""
    if isinstance(data.get("refunds"), list):
        return list(data["refunds"])
    mode = data.get("refund_mode")
    if mode in (None, ""):
        return None
    return [{"mode": mode, "amount": data.get("refund_amount")}]
