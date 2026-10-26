"""BB-048: no secrets or personal data in logs.

Two layers: a repo-wide scan that fails when a logging call passes a password, token, OTP, PIN
or key, and core.log_redaction.RedactingFormatter on every console handler as the safety net.
"""

from __future__ import annotations

import ast
import logging
import re
import sys
from pathlib import Path

import pytest
from django.conf import settings

from core.log_redaction import RedactingFormatter, redact

BACKEND = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("raw", "secret"),
    [
        ('login failed {"email": "x", "password": "hunter2-Secret"}', "hunter2-Secret"),
        ("{'otp': '493021', 'phone': 'x'}", "493021"),
        ("GET /reset?token=abcDEF123456789&next=/", "abcDEF123456789"),
        ("Authorization: Bearer abc.def-ghi_123456789", "abc.def-ghi_123456789"),
        ("cookie eyJhbGciOiJIUzI1NiJ9.eyJ1aWQiOjF9.sig_abcdEFGH seen", "eyJhbGciOiJIUzI1NiJ9"),
        ("mfaToken='eyJ1aWQiOjF9:1xKAD4:1IXOYz'", "1IXOYz"),
        ("api_key=sk_live_51HxYzAbCdEf", "sk_live_51HxYzAbCdEf"),
        ("customer ravi.kumar@example.com wrote", "ravi.kumar@example.com"),
        ("call +91 9876543210 now", "9876543210"),
        ("call 9876543210 now", "9876543210"),
        ("PAN ABCDE1234F on file", "ABCDE1234F"),
        ("aadhaar 2345 6789 0123 given", "2345 6789 0123"),
        ("card 4111 1111 1111 1111 used", "4111 1111 1111 1111"),
    ],
)
def test_secrets_and_personal_data_are_masked(raw, secret):
    out = redact(raw)
    assert secret not in out, out


@pytest.mark.parametrize(
    "text",
    [
        '{"event":"request","request_id":"0832cefc-2a54-4a46-9b8e-965c8bd197a7","method":"GET","path":"/api/v1/dashboard/","status":429,"duration_ms":20}',
        "GSTIN 29ABCDE1234F1ZW on invoice INV/2026-27/0042",
        "Completed invoice 1287 for 118.00 on 2026-10-15",
        "order 123456789012345 total 9999",  # long non-Luhn number is not a card
        "pincode 560001; shipping to Bengaluru",
    ],
)
def test_operational_detail_stays_readable(text):
    assert redact(text) == text


def test_formatter_masks_tracebacks_too():
    fmt = RedactingFormatter("{levelname} {message}", style="{")
    try:
        raise ValueError("bad payload {'password': 'p@ss-Word-9'}")
    except ValueError:
        record = logging.LogRecord("x", logging.ERROR, __file__, 1, "boom for %s", ("a@b.co",), sys.exc_info())
    out = fmt.format(record)
    assert "p@ss-Word-9" not in out and "a@b.co" not in out
    assert "Traceback" in out and "ValueError" in out


def test_every_console_formatter_redacts():
    formatters = settings.LOGGING["formatters"]
    handlers = settings.LOGGING["handlers"]
    for name, handler in handlers.items():
        fmt = formatters[handler["formatter"]]
        assert fmt.get("()") == "core.log_redaction.RedactingFormatter", f"handler {name} logs unredacted"


_SENSITIVE = re.compile(
    r"(pass(word|wd)?$|secret|token|otp|(^|_)pin($|_)|api_?key|private_?key|fernet|pepper|authorization|cookie|aadhaar|card_?number|cvv)",
    re.I,
)
# Names that describe a secret without holding it.
_HARMLESS = re.compile(r"(count|len|_ids?$|kind|type|name|status|mode|enabled|configured|present|exists|expir|age$|ttl|attempt|reason|has_|is_|_key$|label|scope|hint|url)", re.I)
_LOG_METHODS = {"debug", "info", "warning", "error", "exception", "critical", "log"}


def _sensitive_names(node) -> list[str]:
    names = [n.id for n in ast.walk(node) if isinstance(n, ast.Name)]
    names += [n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)]
    return [n for n in names if _SENSITIVE.search(n) and not _HARMLESS.search(n)]


def test_no_logging_call_passes_a_secret():
    offenders = []
    for path in BACKEND.rglob("*.py"):
        parts = set(path.relative_to(BACKEND).parts)
        if parts & {".venv", "migrations", "tests", "node_modules"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for call in ast.walk(tree):
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and call.func.attr in _LOG_METHODS and "log" in ast.unparse(call.func.value).lower()):
                continue
            values = list(call.args[1:]) + [k.value for k in call.keywords if k.arg not in ("exc_info", "stack_info")]
            if call.args and isinstance(call.args[0], ast.JoinedStr):
                values.append(call.args[0])
            for value in values:
                bad = _sensitive_names(value)
                if bad:
                    offenders.append(f"{path.relative_to(BACKEND)}:{call.lineno} logs {bad}")
    assert offenders == [], "\n".join(offenders)
