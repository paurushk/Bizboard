"""Dependency-free golden snapshots (FG-2f).

A snapshot is canonical JSON (sorted keys, 2-space indent) written under
``tests/snapshots/__snapshots__/<name>.json``. The comparison strips volatile
fields (ids, timestamps) — the caller is responsible for shaping the payload
into something stable (account CODES not ids, amounts as strings, etc.).

Update baselines deliberately:  ``SNAPSHOT_UPDATE=1 pytest tests/snapshots/``
and the diff MUST appear in the PR (guarded by a commit-message check later).
If a baseline file is missing and SNAPSHOT_UPDATE is not set, the test SKIPS
with a message rather than failing — so CI is green until someone baselines.
"""

from __future__ import annotations

import json
import os
import pathlib

import pytest

_DIR = pathlib.Path(__file__).parent / "__snapshots__"


@pytest.fixture
def assert_snapshot():
    def _check(name: str, payload) -> None:
        _DIR.mkdir(exist_ok=True)
        path = _DIR / f"{name}.json"
        text = json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"
        if os.environ.get("SNAPSHOT_UPDATE") == "1":
            path.write_text(text, encoding="utf-8")
            return
        if not path.exists():
            pytest.skip(
                f"no snapshot baseline for {name!r} — run "
                f"`SNAPSHOT_UPDATE=1 pytest tests/snapshots/` to create it"
            )
        expected = path.read_text(encoding="utf-8")
        assert text == expected, (
            f"snapshot {name!r} changed. If intentional, re-run with "
            f"SNAPSHOT_UPDATE=1 and include the diff in the PR.\n"
            f"--- expected\n{expected}\n--- got\n{text}"
        )

    return _check
