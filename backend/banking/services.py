"""AA transaction reconciliation hooks (Wave 17F)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Exists, OuterRef, Q

from banking.models import AaTransaction
from payments.models import CustomerReceipt, ReceiptStatus


def match_aa_to_receipts(*, company, tolerance: Decimal | None = None) -> int:
    """Match unmatched AA credits to posted customer receipts.
    Uses reference / UTR match, date proximity (+/- 7 days), and amount tolerance.
    """
    tol = tolerance if tolerance is not None else Decimal("0.01")
    matched = 0
    with transaction.atomic():
        unmatched = list(
            AaTransaction.objects.select_for_update()
            .filter(company=company, matched_payment__isnull=True, amount__gt=0)
            .select_related("consent")
        )
        for aa_txn in unmatched:
            low = aa_txn.amount - tol
            high = aa_txn.amount + tol
            already = Exists(AaTransaction.objects.filter(matched_payment_id=OuterRef("pk")))
            base_qs = (
                CustomerReceipt.objects.select_for_update()
                .filter(
                    company=company,
                    status=ReceiptStatus.POSTED,
                    amount__gte=low,
                    amount__lte=high,
                )
                .filter(~already)
            )

            txn_date = aa_txn.txn_date
            if txn_date:
                base_qs = base_qs.filter(
                    receipt_date__gte=txn_date - timedelta(days=7),
                    receipt_date__lte=txn_date + timedelta(days=7),
                )
            receipt = None
            ref = (aa_txn.txn_id or "").strip()
            if ref and len(ref) >= 6:
                receipt = base_qs.filter(
                    Q(reference__icontains=ref) | Q(utr__icontains=ref) | Q(notes__icontains=ref)
                ).first()
            if not receipt:
                continue
            aa_txn.matched_payment = receipt
            aa_txn.save(update_fields=["matched_payment", "updated_at"])
            matched += 1
    return matched
