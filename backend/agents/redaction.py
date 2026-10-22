"""PII handling for anything sent to a model or stored in step records.

* Key-based redaction mirrors insights.assistant._redact_tool_result_for_llm.
* Free-text scrubbing removes phone numbers, GSTIN, PAN, IFSC, account numbers, UPI ids and emails
  embedded in strings (notes, pasted orders, bill text).
* Masking keeps a fact usable without the raw identifier: ``mask_tail("29ABCDE1234F1Z5") == "…1Z5"``.
"""

from __future__ import annotations

import re
from typing import Any

PII_KEYS = frozenset({
    "email", "phone", "mobile", "gstin", "pan", "address", "proposed_action",
    "bank_account", "account_number", "ifsc", "upi", "aadhaar",
})

_GSTIN = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")
_PAN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
_IFSC = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")
_EMAIL = re.compile(r"\b[\w.+\-]+@[\w\-]+\.[\w.\-]+\b")
_UPI = re.compile(r"\b[\w.\-]{2,}@(?:ok\w+|ybl|paytm|upi|ibl|axl|apl|sbi|hdfcbank|icici)\b", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\d)(?:\+?91[\s\-]?)?[6-9]\d{4}[\s\-]?\d{5}(?!\d)")
_ACCOUNT = re.compile(r"(?<!\d)\d{9,18}(?!\d)")


def mask_tail(value: str, keep: int = 3) -> str:
    value = str(value or "")
    if len(value) <= keep:
        return "…"
    return "…" + value[-keep:]


def scrub_text(text: str) -> str:
    """Replace identifiers inside free text with placeholders. Order matters: UPI/email before generic."""
    text = str(text or "")
    text = _UPI.sub("[upi]", text)
    text = _EMAIL.sub("[email]", text)
    text = _GSTIN.sub("[gstin]", text)
    text = _PAN.sub("[pan]", text)
    text = _IFSC.sub("[ifsc]", text)
    text = _PHONE.sub("[phone]", text)
    text = _ACCOUNT.sub("[account]", text)
    return text


def redact(value: Any, *, scrub_strings: bool = True) -> Any:
    """Recursively drop PII keys and scrub identifiers inside string values."""
    if isinstance(value, dict):
        return {k: redact(v, scrub_strings=scrub_strings) for k, v in value.items() if str(k).lower() not in PII_KEYS}
    if isinstance(value, (list, tuple)):
        return [redact(v, scrub_strings=scrub_strings) for v in value]
    if isinstance(value, str) and scrub_strings:
        return scrub_text(value)
    return value
