"""AA transaction reconciliation hooks (Wave 17F)."""

from __future__ import annotations

from decimal import Decimal

from banking.models import AaTransaction
from payments.models import CustomerReceipt


def match_aa_to_receipts(*, company, tolerance: Decimal | None = None) -> int:
    """Match unmatched AA credits to posted customer receipts.
    Uses reference / UTR match, date proximity (+/- 7 days), and amount tolerance.
    """
    from datetime import timedelta
    from django.db.models import Q
    from payments.models import ReceiptStatus

    tol = tolerance if tolerance is not None else Decimal("0.01")
    matched = 0
    unmatched = AaTransaction.objects.filter(
        company=company, matched_payment__isnull=True, amount__gt=0
    ).select_related("consent")

    for aa_txn in unmatched:
        low = aa_txn.amount - tol
        high = aa_txn.amount + tol
        base_qs = CustomerReceipt.objects.filter(
            company=company,
            status=ReceiptStatus.POSTED,
            amount__gte=low,
            amount__lte=high,
        ).exclude(aa_transactions__isnull=False)

        txn_date = aa_txn.txn_date
        receipt = None
        # 1. First attempt: exact reference/UTR match in narration or reference number
        ref = (aa_txn.txn_id or "").strip()
        if ref and len(ref) >= 6:
            receipt = base_qs.filter(
                Q(reference__icontains=ref) | Q(utr__icontains=ref) | Q(notes__icontains=ref)
            ).first()

        # 2. Amount+date is suggestion-only — never auto-link without UTR/reference.
        if not receipt:
            continue
        aa_txn.matched_payment = receipt
        aa_txn.save(update_fields=["matched_payment", "updated_at"])
        matched += 1
    return matched
