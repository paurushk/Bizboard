"""AA transaction reconciliation hooks (Wave 17F).

INTG-02: match on a UTR/RRN parsed from the narration and on a single
amount+date candidate, not only on `reference == txn_id` (which is the bank's
internal id, never the customer-entered UTR).
INTG-03: each AA row is matched in its own short transaction and only its
matched receipt is row-locked — no blanket `select_for_update` over every
unmatched row and candidate.
"""

from __future__ import annotations

import re
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Exists, OuterRef, Q

from banking.models import AaTransaction
from payments.models import CustomerReceipt, ReceiptStatus

# 12-digit UTR/RRN, or NEFT/IMPS/UPI ref tokens embedded in a narration.
_UTR_RE = re.compile(r"\b([A-Z]{0,4}\d{9,22})\b")
_MIN_REF_LEN = 8


def _candidate_refs(aa_txn) -> list[str]:
    refs: list[str] = []
    tid = (aa_txn.txn_id or "").strip()
    if len(tid) >= _MIN_REF_LEN:
        refs.append(tid)
    narration = ""
    raw = aa_txn.raw if isinstance(aa_txn.raw, dict) else {}
    narration = str(raw.get("narration") or raw.get("txnNote") or "")
    for m in _UTR_RE.findall(narration.upper()):
        if len(m) >= _MIN_REF_LEN and m not in refs:
            refs.append(m)
    # An explicit UTR field on the AA payload, if the FIU provided one.
    for key in ("utr", "rrn", "reference", "ref_no", "txnRef"):
        val = str(raw.get(key) or "").strip()
        if len(val) >= _MIN_REF_LEN and val not in refs:
            refs.append(val)
    return refs


def _match_one(company, aa_txn_id, tol: Decimal) -> str | None:
    """Match a single AA row inside its own transaction. Returns the match
    method ('ref' | 'amount_date') or None."""
    with transaction.atomic():
        try:
            aa_txn = (
                AaTransaction.objects.select_for_update()
                .select_related("consent")
                .get(pk=aa_txn_id, matched_payment__isnull=True, amount__gt=0)
            )
        except AaTransaction.DoesNotExist:
            return None

        low, high = aa_txn.amount - tol, aa_txn.amount + tol
        not_taken = ~Exists(AaTransaction.objects.filter(matched_payment_id=OuterRef("pk")))
        base_qs = CustomerReceipt.objects.filter(
            company=company,
            status=ReceiptStatus.POSTED,
            amount__gte=low,
            amount__lte=high,
        ).filter(not_taken)
        if aa_txn.txn_date:
            base_qs = base_qs.filter(
                receipt_date__gte=aa_txn.txn_date - timedelta(days=7),
                receipt_date__lte=aa_txn.txn_date + timedelta(days=7),
            )

        method = None
        receipt = None
        refs = _candidate_refs(aa_txn)
        if refs:
            ref_q = Q()
            for r in refs:
                ref_q |= Q(reference__iexact=r) | Q(utr__iexact=r)
            receipt = base_qs.filter(ref_q).select_for_update().first()
            if receipt is not None:
                method = "ref"
        if receipt is None:
            # INTG-02: fall back to a *unique* amount+date candidate. Ambiguous
            # (2+) candidates are left for a human — never guess.
            # B4-025: a receipt already confirmed against a bank line (ReconMatch)
            # must not be re-matched by the weak amount+date rule — it only stays
            # eligible for an exact ref/UTR match above.
            candidates = list(
                base_qs.filter(recon_matches__isnull=True).order_by("id")[:2]
            )
            if len(candidates) == 1:
                receipt = (
                    CustomerReceipt.objects.select_for_update().get(pk=candidates[0].pk)
                )
                method = "amount_date"
        if receipt is None:
            return None

        aa_txn.matched_payment = receipt
        raw = aa_txn.raw if isinstance(aa_txn.raw, dict) else {}
        aa_txn.raw = {**raw, "_match_method": method}
        aa_txn.save(update_fields=["matched_payment", "raw", "updated_at"])
        return method


def match_aa_to_receipts(*, company, tolerance: Decimal | None = None) -> int:
    """Match unmatched AA credits to posted customer receipts by UTR/RRN
    (txn id, narration, explicit fields) and, failing that, a unique
    amount+date candidate within ±7 days."""
    tol = tolerance if tolerance is not None else Decimal("0.01")
    ids = list(
        AaTransaction.objects.filter(
            company=company, matched_payment__isnull=True, amount__gt=0
        ).values_list("pk", flat=True)
    )
    matched = 0
    for aa_id in ids:
        if _match_one(company, aa_id, tol) is not None:
            matched += 1
    return matched
