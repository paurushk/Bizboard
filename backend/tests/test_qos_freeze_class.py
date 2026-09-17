"""1.3 — open Q-OS items keep a valid priority; Table B stays deferred (not P0)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BACKLOG = ROOT / "qos" / "backlog"
CLASS = ROOT / "docs" / "ops" / "QOS_FREEZE_CLASS.md"

OPEN_STATES = {"open", "investigating", "in_progress"}
PRIO = re.compile(r"^P[0-3](-investigate|-confirm)?$")

# Table B / out-of-freeze — must stay classified and must not be P0.
FREEZE_DEFERRED = {
    "QOS-0028": "ARCH-07",
    "QOS-0042": "GSTR",
    "QOS-0046": "WhatsApp",
}


def _items():
    rows = []
    for path in sorted(BACKLOG.glob("QOS-*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        data["_path"] = path
        rows.append(data)
    return rows


def test_every_qos_item_has_valid_priority():
    missing = []
    for it in _items():
        prio = it.get("priority")
        if not isinstance(prio, str) or not PRIO.match(prio):
            missing.append(it.get("id", it["_path"].name))
    assert missing == [], missing


def test_open_table_b_items_are_not_p0_and_are_listed():
    text = CLASS.read_text(encoding="utf-8")
    assert CLASS.stat().st_size >= 200
    by_id = {it["id"]: it for it in _items()}
    for iid, token in FREEZE_DEFERRED.items():
        it = by_id[iid]
        assert it["lifecycle"] in OPEN_STATES | {"accepted_wontfix"}
        assert not str(it["priority"]).startswith("P0"), iid
        assert iid in text
        assert token in text


def test_no_open_qos_is_p0():
    p0 = [
        it["id"]
        for it in _items()
        if it.get("lifecycle") in OPEN_STATES and str(it.get("priority", "")).startswith("P0")
    ]
    assert p0 == [], p0
