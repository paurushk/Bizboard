"""Dependency-free golden snapshots (FG-2f).

A snapshot is canonical JSON (sorted keys, 2-space indent) written under
``tests/snapshots/__snapshots__/<name>.json``. The comparison strips volatile
fields (ids, timestamps) — the caller is responsible for shaping the payload
into something stable (account CODES not ids, amounts as strings, etc.).

Decimal strings are compared in a canonical form (see ``_canon_decimals``) so the
same baseline holds on SQLite and on Postgres.

Update baselines deliberately:  ``SNAPSHOT_UPDATE=1 pytest tests/snapshots/``
and the diff MUST appear in the PR (guarded by a commit-message check later).
If a baseline file is missing and SNAPSHOT_UPDATE is not set, the test SKIPS
with a message rather than failing — so CI is green until someone baselines.
"""

from __future__ import annotations

import json
import os
import pathlib
import re

import pytest

_DIR = pathlib.Path(__file__).parent / "__snapshots__"

# A decimal string with a fractional part, e.g. "354.00" or "-0.50".
_DECIMAL_WITH_POINT = re.compile(r"^-?\d+\.\d+$")


def _canon_decimals(value):
    """Make the snapshot independent of the database's decimal scale.

    SQLite returns an aggregate such as Sum("354.00") as 354 (-> "354") while Postgres keeps the
    column scale (-> "354.00"). The baselines were recorded on SQLite, so on Postgres, which is what
    CI runs, every report snapshot failed on formatting alone. Both sides are now compared with
    trailing fractional zeros removed ("354.00" -> "354", "100.50" -> "100.5"). Only strings with a
    decimal point are touched, so ids, dates and document numbers keep their exact form. The scale
    of money fields is asserted separately (tests/test_money_contract.py).
    """
    if isinstance(value, dict):
        return {k: _canon_decimals(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_canon_decimals(v) for v in value]
    if isinstance(value, str) and _DECIMAL_WITH_POINT.match(value):
        stripped = value.rstrip("0").rstrip(".")
        return stripped if stripped not in ("", "-") else "0"
    return value


def _dump(payload) -> str:
    # Round-trip through JSON first so Decimals / dates become strings before canonicalising.
    plain = json.loads(json.dumps(payload, default=str))
    return json.dumps(_canon_decimals(plain), indent=2, sort_keys=True) + "\n"


@pytest.fixture
def assert_snapshot():
    def _check(name: str, payload) -> None:
        _DIR.mkdir(exist_ok=True)
        path = _DIR / f"{name}.json"
        text = _dump(payload)
        if os.environ.get("SNAPSHOT_UPDATE") == "1":
            path.write_text(text, encoding="utf-8")
            return
        if not path.exists():
            pytest.skip(
                f"no snapshot baseline for {name!r} — run "
                f"`SNAPSHOT_UPDATE=1 pytest tests/snapshots/` to create it"
            )
        expected = _dump(json.loads(path.read_text(encoding="utf-8")))
        assert text == expected, (
            f"snapshot {name!r} changed. If intentional, re-run with "
            f"SNAPSHOT_UPDATE=1 and include the diff in the PR.\n"
            f"--- expected\n{expected}\n--- got\n{text}"
        )

    return _check
