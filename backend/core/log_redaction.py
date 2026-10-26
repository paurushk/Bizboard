"""BB-048: keep secrets and personal data out of log output.

``RedactingFormatter`` is the formatter of every console handler (``settings.LOGGING``). It
redacts the fully formatted line, traceback included, so a value that reaches a log through an
exception message or a third-party library is caught as well as one in our own calls.
``tests/test_log_redaction.py`` also scans the code so no logging call passes a password,
token, OTP or key in the first place; this is the safety net behind that rule.

Kept readable on purpose: GSTINs (public business identifiers), request IDs, amounts, dates.
"""

from __future__ import annotations

import logging
import re

_SECRET_KEYS = (
    r"password|passwd|secret|token|access|refresh|otp|pin|api[_-]?key|private[_-]?key|"
    r"authorization|cookie|csrf(?:token|middlewaretoken)?|sessionid|signature|mfa[_-]?token|enrol[_-]?token"
)

_RULES: tuple[tuple[re.Pattern, str], ...] = (
    # "password": "x" / 'token': 'x' (JSON and repr of dicts)
    (re.compile(rf"""(["']?(?:\w*?)(?:{_SECRET_KEYS})["']?\s*[:=]\s*)(["'])(?:(?!\2).)*\2""", re.I), r"\1\2[redacted]\2"),
    # password=x, token=x in query strings and key=value text
    (re.compile(rf"""(\b\w*?(?:{_SECRET_KEYS})=)[^\s&,;"']+""", re.I), r"\1[redacted]"),
    # Authorization headers
    (re.compile(r"\b(Bearer|Basic|Token)\s+[A-Za-z0-9._~+/=-]{8,}", re.I), r"\1 [redacted]"),
    # JSON Web Tokens anywhere
    (re.compile(r"\beyJ[\w-]{5,}\.[\w-]{5,}\.[\w-]{5,}"), "[jwt]"),
    # e-mail addresses: keep the first letter and the domain
    (re.compile(r"\b([A-Za-z0-9])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b"), r"\1***@\2"),
    # Indian mobile numbers (not inside a UUID or a longer number): keep the last two digits
    (re.compile(r"(?<![\w-])(?:\+?91[\s-]?)?[6-9]\d{7}(\d{2})(?![\w-])"), r"[phone **\1]"),
    # PAN on its own (a GSTIN carries a PAN after two digits, so a digit before it is skipped)
    (re.compile(r"(?<![A-Za-z0-9])[A-Z]{5}\d{4}[A-Z](?![A-Za-z0-9])"), "[PAN]"),
    # Aadhaar: 12 digits, optionally grouped 4-4-4, first digit 2-9
    (re.compile(r"(?<![\d-])[2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4}(?![\d-])"), "[aadhaar]"),
)

_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


def _mask_card(match: re.Match) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    if 13 <= len(digits) <= 19 and _luhn_ok(digits):
        return f"[card **{digits[-4:]}]"
    return match.group(0)


def redact(text: str) -> str:
    if not text:
        return text
    text = _CARD.sub(_mask_card, text)
    for pattern, replacement in _RULES:
        text = pattern.sub(replacement, text)
    return text


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))
