"""SET-21: what changed, for the audit trail of Settings.

``snapshot`` reads the fields a write is about to touch; ``changes`` compares it with the result.
Anything that looks like a secret is recorded as "changed" only, never with its value, so the history
shown to owners cannot leak a key, salt, password or account number.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable

_SECRET = re.compile(r"secret|password|credential|token|salt|account_number|api_key|key_id|merchant_key", re.I)
_MAX = 200


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (list, tuple, dict)):
        text = str(value)
    elif hasattr(value, "pk"):
        return value.pk
    else:
        text = str(value)
    return text if len(text) <= _MAX else text[: _MAX - 1] + "…"


def snapshot(instance, fields: Iterable[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in fields:
        if hasattr(instance, name):
            out[name] = getattr(instance, name)
    return out


def changes(before: dict[str, Any], after: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """``{field: {"from": x, "to": y}}`` for each field whose value differs; secrets carry no values."""
    out: dict[str, dict[str, Any]] = {}
    for name, old in before.items():
        new = after.get(name, old)
        if _plain(old) == _plain(new):
            continue
        if _SECRET.search(name):
            out[name] = {"changed": True}
        else:
            out[name] = {"from": _plain(old), "to": _plain(new)}
    return out


def diff_instance(instance, fields: Iterable[str], before: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Compare a ``snapshot`` taken before a save with the instance after it."""
    return changes(before, snapshot(instance, before.keys()))
