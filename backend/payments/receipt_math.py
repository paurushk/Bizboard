"""One definition of what a customer receipt has left, and how its discount and TDS are spread.

Everything that needs "how much of this receipt is still unallocated" or "how much of its
discount does this allocation clear" calls here, so the GL posting, the ledger, the receipts
screen, the CSV, the summary and the period-close tie-outs cannot disagree.

Terms
-----
* ``cash``     – ``PaymentAllocation.amount`` (money applied to the invoice).
* ``discount`` – ``PaymentAllocation.discount_applied`` (settlement discount cleared, no cash).
* ``tds``      – ``PaymentAllocation.tds_applied`` (customer-deducted TDS cleared, no cash).

An invoice is reduced by ``cash + discount + tds``. Customer Advances (2300) is credited with
``receipt.amount + receipt.tds_deducted`` when the receipt posts and debited by ``cash + tds``
when it is allocated; the discount never touches 2300 (it posts at allocation time).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Sum

ZERO = Decimal("0")
PAISE = Decimal("0.01")


def _d(value) -> Decimal:
    return Decimal(str(value or 0))


def _round(value: Decimal) -> Decimal:
    return value.quantize(PAISE, rounding=ROUND_HALF_UP)


class LiveTotals:
    """Sums over a receipt's live (unreversed) allocations."""

    __slots__ = ("cash", "discount", "tds")

    def __init__(self, cash=ZERO, discount=ZERO, tds=ZERO):
        self.cash = _d(cash)
        self.discount = _d(discount)
        self.tds = _d(tds)

    @classmethod
    def from_rows(cls, rows) -> "LiveTotals":
        """From allocation objects (e.g. a prefetched ``allocations.all()``)."""
        totals = cls()
        for row in rows:
            if getattr(row, "reversed_at", None) is not None:
                continue
            totals.cash += _d(row.amount)
            totals.discount += _d(row.discount_applied)
            totals.tds += _d(row.tds_applied)
        return totals

    @classmethod
    def from_db(cls, receipt, *, exclude_pk=None) -> "LiveTotals":
        from payments.models import PaymentAllocation

        qs = PaymentAllocation.objects.filter(receipt=receipt, reversed_at__isnull=True)
        if exclude_pk:
            qs = qs.exclude(pk=exclude_pk)
        agg = qs.aggregate(c=Sum("amount"), d=Sum("discount_applied"), t=Sum("tds_applied"))
        return cls(agg["c"], agg["d"], agg["t"])


def refunded_total(receipt) -> Decimal:
    """Live (not voided) advance refunds paid out of this receipt."""
    from payments.models import AdvanceRefundStatus, CustomerAdvanceRefund

    return _d(
        CustomerAdvanceRefund.objects.filter(receipt=receipt, status=AdvanceRefundStatus.POSTED)
        .aggregate(t=Sum("amount"))["t"]
    )


def live_refunds_by_receipt(receipt_ids) -> dict[int, Decimal]:
    """{receipt id: live advance refunds}, one query, for list/statement readers."""
    from payments.models import AdvanceRefundStatus, CustomerAdvanceRefund

    ids = list(receipt_ids)
    if not ids:
        return {}
    rows = (
        CustomerAdvanceRefund.objects.filter(receipt_id__in=ids, status=AdvanceRefundStatus.POSTED)
        .values("receipt_id")
        .annotate(t=Sum("amount"))
    )
    return {row["receipt_id"]: _d(row["t"]) for row in rows}


def shares_for(receipt, cash, live: LiveTotals, refunds: Decimal | None = None) -> tuple[Decimal, Decimal]:
    """(discount, tds) that an allocation of ``cash`` clears, given the receipt's live totals.

    Proportional to the cash share of ``receipt.amount``, rounded to paise and never above what
    is still unapplied; the allocation that brings cumulative cash up to ``receipt.amount`` takes
    the remainder, so across any split the shares add up to the receipt's discount and TDS to
    the paisa. Cash handed back as an advance refund is out of the base, so a part-refunded
    receipt still clears its whole discount once the rest of its cash is applied.
    """
    cash = _d(cash)
    refunds = refunded_total(receipt) if refunds is None else refunds
    base = _d(receipt.amount) - refunds
    if cash <= 0 or base <= 0:
        return ZERO, ZERO
    completes = live.cash + cash >= base

    def one(total, applied):
        total = _d(total)
        left = total - applied
        if total <= 0 or left <= 0:
            return ZERO
        share = left if completes else _round(cash / base * total)
        return max(ZERO, min(share, left))

    return one(receipt.settlement_discount, live.discount), one(receipt.tds_deducted, live.tds)


def max_cash_for_balance(receipt, balance, remaining_cash, live: LiveTotals) -> Decimal:
    """Largest cash allocation ``x <= remaining_cash`` with ``x + discount + tds <= balance``."""
    balance = _d(balance)
    refunds = refunded_total(receipt)
    hi = int(_round(min(_d(remaining_cash), balance)) * 100)
    lo = 0
    while lo < hi:
        mid = (lo + hi + 1) // 2
        cash = Decimal(mid) / 100
        discount, tds = shares_for(receipt, cash, live, refunds)
        if cash + discount + tds <= balance:
            lo = mid
        else:
            hi = mid - 1
    return Decimal(lo) / 100


def cash_available(receipt, live: LiveTotals | None = None, refunds: Decimal | None = None) -> Decimal:
    """Cash of the receipt not yet allocated and not refunded (what may still be applied)."""
    live = live or LiveTotals.from_db(receipt)
    refunds = refunded_total(receipt) if refunds is None else refunds
    return max(ZERO, _d(receipt.amount) - live.cash - refunds)


def receipt_unallocated(receipt, live: LiveTotals | None = None, refunds: Decimal | None = None) -> Decimal:
    """The receipt's balance in Customer Advances (2300) terms.

    ``amount + tds_deducted - sum(cash + tds applied) - live refunds``. Equals the GL credit
    still sitting on the advance account for this receipt.
    """
    live = live or LiveTotals.from_db(receipt)
    refunds = refunded_total(receipt) if refunds is None else refunds
    return _d(receipt.amount) + _d(receipt.tds_deducted) - live.cash - live.tds - refunds
