"""AA transaction reconciliation hooks (Wave 17F).

INTG-02: match on a UTR/RRN parsed from the narration and on a single
amount+date candidate, not only on `reference == txn_id` (which is the bank's
internal id, never the customer-entered UTR).
INTG-03: each AA row is matched in its own short transaction and only its
matched receipt is row-locked — no blanket `select_for_update` over every
unmatched row and candidate.

Credits bind a customer receipt only when a normalised UTR is uniquely equal,
or when amount+date is unique, or when a narration party token is unique.
A substring that is not an equal UTR never auto-binds. Debits bind a supplier
payment or expense the same way. An expired consent is refused.
"""

from __future__ import annotations

import re
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q

from banking.models import AaConsent, AaTransaction
from payments.models import CustomerReceipt, ReceiptStatus, SupplierPayment, SupplierPaymentStatus
from payments.upi import normalize_utr

# 12-digit UTR/RRN, or NEFT/IMPS/UPI ref tokens embedded in a narration.
_UTR_RE = re.compile(r"\b([A-Z]{0,4}\d{9,22})\b")
_MIN_REF_LEN = 8
_PARTY_STOP = frozenset({
    "THE", "AND", "FOR", "FROM", "WITH", "PVT", "LTD", "LIMITED", "PRIVATE",
    "NEFT", "IMPS", "RTGS", "UPI", "CMS", "TRANSFER", "PAYMENT",
    "CREDIT", "DEBIT", "INDIA", "BANK", "FUNDS", "CLEARING", "ACCOUNT",
    "INF", "TO", "BY", "ACCT",
})
_OPEN_CONSENT = (AaConsent.Status.PENDING, AaConsent.Status.ACTIVE)
_CLOSED_CONSENT = (AaConsent.Status.EXPIRED, AaConsent.Status.REVOKED)
_CONSENT_CLOSED_MSG = (
    "Account Aggregator consent has expired. Fetch and match are refused "
    "until the consent is renewed."
)


def _amount_date_deltas(aa_txn, receipt) -> tuple:
    amt_delta = abs(Decimal(str(receipt.amount or 0)) - abs(aa_txn.amount))
    target_date = getattr(receipt, "receipt_date", None) or getattr(receipt, "payment_date", None)
    if target_date is None:
        target_date = getattr(receipt, "expense_date", None)
    if aa_txn.txn_date and target_date:
        date_delta = abs((target_date - aa_txn.txn_date).days)
    else:
        date_delta = 10**6
    return amt_delta, date_delta, receipt.pk


def _rank_rows(aa_txn, rows) -> list:
    """R-043: |amount-delta| then |date-delta|, then id. Cap is applied after sort."""
    return sorted(rows, key=lambda r: _amount_date_deltas(aa_txn, r))


def _candidate_refs(aa_txn) -> list[str]:
    refs: list[str] = []
    tid = (aa_txn.txn_id or "").strip()
    if len(tid) >= _MIN_REF_LEN:
        refs.append(tid)
    raw = aa_txn.raw if isinstance(aa_txn.raw, dict) else {}
    narration = str(raw.get("narration") or raw.get("txnNote") or "")
    for m in _UTR_RE.findall(narration.upper()):
        if len(m) >= _MIN_REF_LEN and m not in refs:
            refs.append(m)
    for key in ("utr", "rrn", "reference", "ref_no", "txnRef"):
        val = str(raw.get(key) or "").strip()
        if len(val) >= _MIN_REF_LEN and val not in refs:
            refs.append(val)
    return refs


def _narration_text(aa_txn) -> str:
    raw = aa_txn.raw if isinstance(aa_txn.raw, dict) else {}
    return str(raw.get("narration") or raw.get("txnNote") or "")


def _name_tokens(text: str) -> set[str]:
    words = re.split(r"[^A-Za-z0-9]+", (text or "").upper())
    return {w for w in words if len(w) >= 5 and w not in _PARTY_STOP and not w.isdigit()}


def _unique_by_party(aa_txn, rows, name_of) -> object | None:
    """Auto-match only when exactly one row's party shares a narration token."""
    narr = _name_tokens(_narration_text(aa_txn))
    if not narr:
        return None
    hits = [row for row in rows if narr & _name_tokens(name_of(row))]
    if len(hits) == 1:
        return hits[0]
    return None


def _exact_ref_q(refs: list[str]) -> Q:
    q = Q()
    for ref in refs:
        norm = normalize_utr(ref)
        if len(norm) < _MIN_REF_LEN:
            continue
        q |= Q(utr__iexact=norm) | Q(reference__iexact=norm)
    return q


def _date_window(qs, aa_txn, date_field: str):
    if not aa_txn.txn_date:
        return qs
    return qs.filter(**{
        f"{date_field}__gte": aa_txn.txn_date - timedelta(days=7),
        f"{date_field}__lte": aa_txn.txn_date + timedelta(days=7),
    })


def _lock_and_bind_receipt(aa_txn, receipt, method: str) -> str | None:
    receipt = CustomerReceipt.objects.select_for_update().get(pk=receipt.pk)
    if AaTransaction.objects.filter(matched_payment_id=receipt.pk).exclude(pk=aa_txn.pk).exists():
        return None
    aa_txn.matched_payment = receipt
    return _save_match(aa_txn, method)


def _lock_and_bind_supplier(aa_txn, payment, method: str) -> str | None:
    payment = SupplierPayment.objects.select_for_update().get(pk=payment.pk)
    if (
        AaTransaction.objects.filter(matched_supplier_payment_id=payment.pk)
        .exclude(pk=aa_txn.pk)
        .exists()
    ):
        return None
    aa_txn.matched_supplier_payment = payment
    return _save_match(aa_txn, method)


def _lock_and_bind_expense(aa_txn, expense, method: str) -> str | None:
    from accounting.models import Expense

    expense = Expense.objects.select_for_update().get(pk=expense.pk)
    if AaTransaction.objects.filter(matched_expense_id=expense.pk).exclude(pk=aa_txn.pk).exists():
        return None
    aa_txn.matched_expense = expense
    return _save_match(aa_txn, method)


def _save_match(aa_txn, method: str) -> str | None:
    raw = aa_txn.raw if isinstance(aa_txn.raw, dict) else {}
    aa_txn.raw = {**raw, "_match_method": method}
    try:
        with transaction.atomic():
            aa_txn.save(update_fields=[
                "matched_payment", "matched_supplier_payment", "matched_expense",
                "raw", "updated_at",
            ])
    except IntegrityError:
        return None
    return method


def _match_credit(company, aa_txn, tol: Decimal) -> str | None:
    low, high = aa_txn.amount - tol, aa_txn.amount + tol
    not_taken = ~Exists(AaTransaction.objects.filter(matched_payment_id=OuterRef("pk")))
    posted = CustomerReceipt.objects.filter(
        company=company, status=ReceiptStatus.POSTED,
    ).filter(not_taken)
    refs = _candidate_refs(aa_txn)
    ref_q = _exact_ref_q(refs)
    if ref_q:
        # A reference alone is not proof: the amount must agree too, or a narration that merely
        # quotes another receipt's UTR would bind a small credit to a large receipt.
        exact = list(posted.filter(ref_q, amount__gte=low, amount__lte=high).select_related("customer"))
        if len(exact) == 1:
            return _lock_and_bind_receipt(aa_txn, exact[0], "ref")
        if len(exact) > 1:
            return None

    base_qs = posted.filter(amount__gte=low, amount__lte=high).select_related("customer")
    base_qs = _date_window(base_qs, aa_txn, "receipt_date")
    ranked = _rank_rows(aa_txn, list(base_qs.filter(recon_matches__isnull=True)))
    if len(ranked) == 1:
        return _lock_and_bind_receipt(aa_txn, ranked[0], "amount_date")
    if len(ranked) > 1:
        party = _unique_by_party(aa_txn, ranked, lambda row: row.customer.name)
        if party is not None:
            return _lock_and_bind_receipt(aa_txn, party, "narration")
    return None


def _match_debit(company, aa_txn, tol: Decimal) -> str | None:
    from accounting.models import Expense

    magnitude = abs(aa_txn.amount)
    low, high = magnitude - tol, magnitude + tol
    not_taken_pay = ~Exists(
        AaTransaction.objects.filter(matched_supplier_payment_id=OuterRef("pk"))
    )
    payments = SupplierPayment.objects.filter(
        company=company, status=SupplierPaymentStatus.POSTED,
    ).filter(not_taken_pay).select_related("supplier")
    refs = _candidate_refs(aa_txn)
    ref_q = _exact_ref_q(refs)
    if ref_q:
        exact = list(payments.filter(ref_q, amount__gte=low, amount__lte=high))
        if len(exact) == 1:
            return _lock_and_bind_supplier(aa_txn, exact[0], "ref")
        if len(exact) > 1:
            return None

    pay_window = _date_window(
        payments.filter(amount__gte=low, amount__lte=high), aa_txn, "payment_date",
    )
    ranked_pay = _rank_rows(
        aa_txn, list(pay_window.filter(recon_matches__isnull=True))
    )
    not_taken_exp = ~Exists(AaTransaction.objects.filter(matched_expense_id=OuterRef("pk")))
    expenses = Expense.objects.filter(company=company).filter(not_taken_exp)
    exp_window = _date_window(
        expenses.filter(amount__gte=low, amount__lte=high), aa_txn, "expense_date",
    )
    ranked_exp = _rank_rows(aa_txn, list(exp_window))

    if len(ranked_pay) == 1 and not ranked_exp:
        return _lock_and_bind_supplier(aa_txn, ranked_pay[0], "amount_date")
    if len(ranked_pay) > 1:
        party = _unique_by_party(aa_txn, ranked_pay, lambda row: row.supplier.name)
        if party is not None:
            return _lock_and_bind_supplier(aa_txn, party, "narration")
        return None
    if len(ranked_exp) == 1 and not ranked_pay:
        return _lock_and_bind_expense(aa_txn, ranked_exp[0], "amount_date")
    if len(ranked_exp) > 1 and not ranked_pay:
        party = _unique_by_party(aa_txn, ranked_exp, lambda row: row.party_name)
        if party is not None:
            return _lock_and_bind_expense(aa_txn, party, "narration")
    return None


def _match_one(company, aa_txn_id, tol: Decimal) -> str | None:
    """Match a single AA row inside its own transaction.

    Returns the match method ('ref' | 'amount_date' | 'narration') or None.
    A second attach to a receipt, supplier payment, or expense is refused.
    """
    from core.exceptions import BusinessRuleError

    with transaction.atomic():
        try:
            aa_txn = (
                AaTransaction.objects.select_for_update()
                .select_related("consent")
                .get(
                    pk=aa_txn_id,
                    matched_payment__isnull=True,
                    matched_supplier_payment__isnull=True,
                    matched_expense__isnull=True,
                )
            )
        except AaTransaction.DoesNotExist:
            return None
        if aa_txn.consent.status in _CLOSED_CONSENT:
            raise BusinessRuleError(_CONSENT_CLOSED_MSG)
        if aa_txn.amount > 0:
            return _match_credit(company, aa_txn, tol)
        if aa_txn.amount < 0:
            return _match_debit(company, aa_txn, tol)
        return None


def _unmatched_qs(company):
    return AaTransaction.objects.filter(
        company=company,
        matched_payment__isnull=True,
        matched_supplier_payment__isnull=True,
        matched_expense__isnull=True,
    )


def match_aa_to_payments(*, company, tolerance: Decimal | None = None) -> int:
    """Pair unmatched debit AA rows with supplier payments or expenses."""
    tol = tolerance if tolerance is not None else Decimal("0.01")
    ids = list(
        _unmatched_qs(company)
        .filter(amount__lt=0, consent__status__in=_OPEN_CONSENT)
        .values_list("pk", flat=True)
    )
    matched = 0
    for aa_id in ids:
        if _match_one(company, aa_id, tol) is not None:
            matched += 1
    return matched


def match_aa_to_receipts(*, company, tolerance: Decimal | None = None) -> int:
    """Match unmatched AA rows.

    Credits: unique normalised UTR equality, else a unique amount+date, else a
    unique narration party token. Debits: the same rules against supplier
    payments and expenses. Substring UTR hits and ambiguous narration hits stay
    unmatched. Expired-consent rows are refused when they are the only backlog.
    """
    from core.exceptions import BusinessRuleError

    open_left = _unmatched_qs(company).filter(consent__status__in=_OPEN_CONSENT)
    expired_left = _unmatched_qs(company).filter(consent__status__in=_CLOSED_CONSENT)
    if (
        expired_left.exists()
        and not open_left.exists()
        # A renewed consent that simply has no new rows is not an error.
        and not AaConsent.objects.filter(company=company, status__in=_OPEN_CONSENT).exists()
    ):
        raise BusinessRuleError(_CONSENT_CLOSED_MSG)

    tol = tolerance if tolerance is not None else Decimal("0.01")
    ids = list(open_left.values_list("pk", flat=True))
    matched = 0
    for aa_id in ids:
        if _match_one(company, aa_id, tol) is not None:
            matched += 1
    return matched
