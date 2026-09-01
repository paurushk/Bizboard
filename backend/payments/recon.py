"""Bank statement matching / reconciliation suggestions (Phase 3.2)."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation


from core.exceptions import BusinessRuleError

from .models import (
    BankLineMatchStatus,
    BankStatementLine,
    CustomerReceipt,
    ReconMatch,
    SupplierPayment,
    SupplierPaymentStatus,
)
from .upi import normalize_utr


def _parse_amount(raw: str) -> Decimal:
    cleaned = (raw or "").strip().replace(",", "")
    if not cleaned:
        return Decimal("0")
    # Handle CR/DR suffixes
    sign = Decimal("1")
    upper = cleaned.upper()
    if upper.endswith("DR") or upper.endswith("DEBIT"):
        sign = Decimal("-1")
        cleaned = re.sub(r"(?i)\s*(DR|DEBIT)\s*$", "", cleaned).strip()
    elif upper.endswith("CR") or upper.endswith("CREDIT"):
        cleaned = re.sub(r"(?i)\s*(CR|CREDIT)\s*$", "", cleaned).strip()
    try:
        return sign * Decimal(cleaned)
    except InvalidOperation:
        raise BusinessRuleError(f"Invalid amount: {raw}")


BANK_PRESETS = {
    "generic": {
        "date": ["date", "txn date", "transaction date", "value date"],
        "amount": ["amount", "txn amount", "transaction amount"],
        "credit": ["credit", "deposit", "cr"],
        "debit": ["debit", "withdrawal", "dr"],
        "narration": ["narration", "description", "remarks", "particulars"],
        "utr": ["utr", "ref no", "reference", "cheque no", "chq/ref number"],
    },
    "hdfc": {
        "date": ["date"],
        "amount": [],
        "credit": ["credit amount"],
        "debit": ["debit amount"],
        "narration": ["narration"],
        "utr": ["chq/ref number", "ref number"],
    },
    "icici": {
        "date": ["transaction date", "value date"],
        "amount": ["amount"],
        "credit": ["credit"],
        "debit": ["debit"],
        "narration": ["transaction remarks", "remarks"],
        "utr": ["cheque number", "reference number"],
    },
    "sbi": {
        "date": ["txn date", "value date"],
        "amount": [],
        "credit": ["credit"],
        "debit": ["debit"],
        "narration": ["description", "narration"],
        "utr": ["ref no.", "ref no"],
    },
}


def _norm_header(h: str) -> str:
    return re.sub(r"\s+", " ", (h or "").strip().lower())


def _pick_col(headers: list[str], aliases: list[str]) -> str | None:
    normalized = {_norm_header(h): h for h in headers}
    for alias in aliases:
        if alias in normalized:
            return normalized[alias]
    return None


def parse_bank_csv(content: str | bytes, preset: str = "generic") -> list[dict]:
    if isinstance(content, bytes):
        content = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise BusinessRuleError("CSV has no header row.")
    headers = list(reader.fieldnames)
    cfg = BANK_PRESETS.get(preset) or BANK_PRESETS["generic"]
    date_col = _pick_col(headers, cfg["date"])
    amount_col = _pick_col(headers, cfg["amount"])
    credit_col = _pick_col(headers, cfg["credit"])
    debit_col = _pick_col(headers, cfg["debit"])
    narr_col = _pick_col(headers, cfg["narration"])
    utr_col = _pick_col(headers, cfg["utr"])
    if not date_col:
        raise BusinessRuleError("Could not find a date column in the CSV.")
    if not amount_col and not (credit_col or debit_col):
        raise BusinessRuleError("Could not find amount/credit/debit columns.")

    rows: list[dict] = []
    for raw in reader:
        date_raw = (raw.get(date_col) or "").strip()
        if not date_raw:
            continue
        # Try ISO then DD/MM/YYYY / DD-MM-YYYY
        txn_date = None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%b-%Y"):
            try:
                from datetime import datetime

                txn_date = datetime.strptime(date_raw, fmt).date()
                break
            except ValueError:
                continue
        if txn_date is None:
            continue

        if amount_col and (raw.get(amount_col) or "").strip():
            amount = _parse_amount(raw.get(amount_col) or "0")
        else:
            credit = _parse_amount(raw.get(credit_col) or "0") if credit_col else Decimal("0")
            debit = _parse_amount(raw.get(debit_col) or "0") if debit_col else Decimal("0")
            amount = credit if credit else (Decimal("-1") * debit)

        narration = (raw.get(narr_col) or "").strip() if narr_col else ""
        utr = normalize_utr(raw.get(utr_col) or "") if utr_col else ""
        # Pull UTR-like tokens from narration
        if not utr:
            m = re.search(r"\b([A-Z0-9]{12,22})\b", narration.upper())
            if m:
                utr = m.group(1)

        line_hash = hashlib.sha256(
            f"{txn_date}|{amount}|{utr}|{narration}".encode()
        ).hexdigest()
        rows.append(
            {
                "txn_date": txn_date,
                "amount": amount,
                "narration": narration[:512],
                "utr": utr,
                "line_hash": line_hash,
            }
        )
    return rows


def score_match(line: BankStatementLine, *, receipt: CustomerReceipt | None = None,
                payment: SupplierPayment | None = None) -> Decimal:
    """Return 0–100 confidence."""
    score = Decimal("0")
    target_amount = None
    target_date = None
    target_utr = ""
    target_ref = ""
    target_name = ""
    if receipt:
        target_amount = receipt.amount
        target_date = receipt.receipt_date
        target_utr = normalize_utr(receipt.utr or receipt.reference)
        target_ref = (receipt.number or "").upper()
        target_name = (receipt.customer.name or "").upper()
        # Credits match receipts
        if line.amount <= 0:
            return Decimal("0")
        if abs(line.amount - target_amount) < Decimal("0.01"):
            score += Decimal("40")
    elif payment:
        target_amount = payment.amount
        target_date = payment.payment_date
        target_utr = normalize_utr(payment.utr or payment.reference)
        target_ref = (payment.number or "").upper()
        target_name = (payment.supplier.name or "").upper()
        if line.amount >= 0:
            return Decimal("0")
        if abs(abs(line.amount) - target_amount) < Decimal("0.01"):
            score += Decimal("40")
    else:
        return Decimal("0")

    line_utr = normalize_utr(line.utr)
    if line_utr and target_utr and line_utr == target_utr:
        score += Decimal("40")
    narr = (line.narration or "").upper()
    if target_ref and target_ref in narr:
        score += Decimal("25")
    if target_name:
        tokens = [t for t in re.split(r"\W+", target_name) if len(t) > 3]
        hits = sum(1 for t in tokens if t in narr)
        if hits:
            score += min(Decimal("15"), Decimal(hits) * Decimal("5"))
    if target_date and abs((line.txn_date - target_date).days) <= 3:
        score += Decimal("10")
    elif target_date and abs((line.txn_date - target_date).days) <= 7:
        score += Decimal("5")
    return min(score, Decimal("100"))


def suggest_matches(*, company, line: BankStatementLine, limit: int = 5) -> list[dict]:
    if line.match_status == BankLineMatchStatus.MATCHED:
        return []
    window_start = line.txn_date - timedelta(days=14)
    window_end = line.txn_date + timedelta(days=14)
    suggestions: list[dict] = []

    if line.amount > 0:
        qs = CustomerReceipt.objects.filter(
            company=company,
            receipt_date__gte=window_start,
            receipt_date__lte=window_end,
            status="POSTED",
        ).select_related("customer")
        # Exclude already matched receipts
        matched_ids = ReconMatch.objects.filter(
            company=company, receipt__isnull=False
        ).values_list("receipt_id", flat=True)
        qs = qs.exclude(id__in=matched_ids)
        for receipt in qs[:50]:
            conf = score_match(line, receipt=receipt)
            if conf >= Decimal("40"):
                suggestions.append(
                    {
                        "type": "receipt",
                        "id": receipt.id,
                        "number": receipt.number,
                        "amount": str(receipt.amount),
                        "date": str(receipt.receipt_date),
                        "party": receipt.customer.name,
                        "confidence": float(conf),
                    }
                )
    else:
        qs = SupplierPayment.objects.filter(
            company=company,
            status=SupplierPaymentStatus.POSTED,
            payment_date__gte=window_start,
            payment_date__lte=window_end,
        ).select_related("supplier")
        matched_ids = ReconMatch.objects.filter(
            company=company, supplier_payment__isnull=False
        ).values_list("supplier_payment_id", flat=True)
        qs = qs.exclude(id__in=matched_ids)
        for payment in qs[:50]:
            conf = score_match(line, payment=payment)
            if conf >= Decimal("40"):
                suggestions.append(
                    {
                        "type": "supplier_payment",
                        "id": payment.id,
                        "number": payment.number,
                        "amount": str(payment.amount),
                        "date": str(payment.payment_date),
                        "party": payment.supplier.name,
                        "confidence": float(conf),
                    }
                )

    suggestions.sort(key=lambda s: s["confidence"], reverse=True)
    return suggestions[:limit]


def _has_hard_recon_anchor(line: BankStatementLine, suggestion: dict) -> bool:
    """Auto-commit requires UTR match or exact receipt/payment number in narration."""
    narr = (line.narration or "").upper()
    number = (suggestion.get("number") or "").upper().strip()
    if number and number in narr:
        return True

    line_utr = normalize_utr(line.utr)
    target_utr = ""
    if suggestion.get("type") == "receipt":
        receipt = CustomerReceipt.objects.filter(pk=suggestion.get("id")).only(
            "utr", "reference"
        ).first()
        if receipt:
            target_utr = normalize_utr(receipt.utr or receipt.reference)
    elif suggestion.get("type") == "supplier_payment":
        payment = SupplierPayment.objects.filter(pk=suggestion.get("id")).only(
            "utr", "reference"
        ).first()
        if payment:
            target_utr = normalize_utr(payment.utr or payment.reference)
    if line_utr and target_utr and line_utr == target_utr:
        return True
    # UTR also accepted when present only in narration.
    if target_utr and target_utr in narr.replace(" ", ""):
        return True
    return False


def is_exact_unique_suggestion(suggestions: list[dict], line: BankStatementLine) -> bool:
    """True when exactly one suggestion has high confidence + exact amount + hard ref."""
    if len(suggestions) != 1:
        return False
    s = suggestions[0]
    if s["confidence"] < 90:
        return False
    amt = Decimal(s["amount"])
    if line.amount > 0:
        amount_ok = abs(line.amount - amt) < Decimal("0.01")
    else:
        amount_ok = abs(abs(line.amount) - amt) < Decimal("0.01")
    if not amount_ok:
        return False
    # Soft score alone is insufficient for auto-commit.
    return _has_hard_recon_anchor(line, s)
