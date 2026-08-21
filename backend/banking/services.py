"""AA transaction reconciliation hooks (Wave 17F)."""

from __future__ import annotations

from decimal import Decimal

from banking.models import AaTransaction
from payments.models import CustomerReceipt


def match_aa_to_receipts(*, company, tolerance: Decimal | None = None) -> int:
    """Match unmatched AA credits to posted customer receipts by amount (+/- tolerance).

    Returns count of newly matched rows.
    """
    tol = tolerance if tolerance is not None else Decimal("0.01")
    matched = 0
    unmatched = AaTransaction.objects.filter(
        company=company, matched_payment__isnull=True, amount__gt=0
    ).select_related("consent")
    for aa_txn in unmatched:
        low = aa_txn.amount - tol
        high = aa_txn.amount + tol
        receipt = (
            CustomerReceipt.objects.filter(
                company=company,
                amount__gte=low,
                amount__lte=high,
            )
            .exclude(aa_transactions__isnull=False)
            .order_by("-receipt_date", "-id")
            .first()
        )
        if receipt:
            aa_txn.matched_payment = receipt
            aa_txn.save(update_fields=["matched_payment", "updated_at"])
            matched += 1
    return matched
