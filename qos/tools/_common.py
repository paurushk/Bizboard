"""Shared helpers for the Q-OS pipeline tools.

Everything reads from ``qos/backlog/*.yaml`` (source of truth) and
``qos/journeys.yaml`` (risk-surface inventory). No framework, no state.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

def enable_utf8_stdout() -> None:
    """Windows consoles default to cp1252; the dashboard prints emoji. Make stdout UTF-8."""
    import sys

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):  # pragma: no cover - non-reconfigurable stream
            pass


REPO_ROOT = Path(__file__).resolve().parents[2]
QOS_DIR = REPO_ROOT / "qos"
BACKLOG_DIR = QOS_DIR / "backlog"
SCHEMA_PATH = QOS_DIR / "schema" / "item.schema.json"
JOURNEYS_PATH = QOS_DIR / "journeys.yaml"
HISTORY_DIR = QOS_DIR / "history"
BACKLOG_DOC = REPO_ROOT / "docs" / "PRODUCT_QUALITY_BACKLOG.md"
STRATEGY_DOC = REPO_ROOT / "docs" / "TESTING_STRATEGY.md"
SOURCE_MAP = BACKLOG_DIR / "_SOURCE_MAP.md"

CATEGORIES = [
    "CRITICAL_BUG", "DISSATISFACTION", "USABILITY", "PERSONA_GAP", "BUSINESS_GAP",
    "RELIABILITY_TRUST", "PERFORMANCE", "SECURITY_PRIVACY", "DELIGHT", "INNOVATION",
]

CATEGORY_LABEL = {
    "CRITICAL_BUG": "Critical bugs",
    "DISSATISFACTION": "User dissatisfaction",
    "USABILITY": "Usability improvements",
    "PERSONA_GAP": "Persona gaps",
    "BUSINESS_GAP": "Business gaps",
    "RELIABILITY_TRUST": "Reliability & trust issues",
    "PERFORMANCE": "Performance improvements",
    "SECURITY_PRIVACY": "Security & privacy fixes",
    "DELIGHT": "Delight opportunities",
    "INNOVATION": "Innovation opportunities",
}

CATEGORY_EMOJI = {
    "CRITICAL_BUG": "\U0001F534",       # red circle
    "DISSATISFACTION": "\U0001F7E0",    # orange circle
    "USABILITY": "\U0001F7E1",          # yellow circle
    "PERSONA_GAP": "\U0001F7E3",        # purple circle
    "BUSINESS_GAP": "\U0001F535",       # blue circle
    "RELIABILITY_TRUST": "\U0001F7E4",  # brown circle
    "PERFORMANCE": "\U0001F7E2",        # green circle
    "SECURITY_PRIVACY": "\U000026AB",   # black circle
    "DELIGHT": "\U00002728",            # sparkles
    "INNOVATION": "\U0001F4A1",         # bulb
}

PERSONAS = ["P1", "P2", "P3", "P4", "P5", "P6"]
ARCHETYPES = ["ARCH-01", "ARCH-02", "ARCH-03", "ARCH-04", "ARCH-05", "ARCH-06", "ARCH-07"]

OPEN_STATES = {"open", "investigating", "in_progress"}
TERMINAL_STATES = {"guarded", "accepted_wontfix"}
FIXED_PLUS = {"fixed", "verified", "guarded"}

# --- impact / priority model (mirror of qos/RUBRIC.md) ---------------------

PRIO_W = {
    "P0": 100, "P0-confirm": 80, "P1": 40, "P1-investigate": 20, "P2": 10, "P3": 3,
}
IMPACT_W = {"High": 3, "Medium": 2, "Low": 1}
EV_CONF = {
    "measured": 1.0, "simulated": 0.9, "single-run": 0.7, "heuristic": 0.5, "hypothesis": 0.3,
}
EFFORT_C = {"S": 1, "M": 3, "L": 8, "XL": 20}

# evidence strength -> the priorities it is allowed to carry
EVIDENCE_PRIORITY_CAP = {
    "measured": {"P0", "P0-confirm", "P1", "P1-investigate", "P2", "P3"},
    "simulated": {"P0", "P0-confirm", "P1", "P1-investigate", "P2", "P3"},
    "single-run": {"P0-confirm", "P1", "P1-investigate", "P2", "P3"},
    "heuristic": {"P1", "P1-investigate", "P2", "P3"},
    "hypothesis": {"P1-investigate", "P2", "P3"},
}


def impact_band(scoring: dict) -> str:
    """High if reach*severity*frequency >= 45 or any severity == 5; Medium 18-44; else Low."""
    r, s, f = scoring["reach"], scoring["severity"], scoring["frequency"]
    product = r * s * f
    if s == 5 or product >= 45:
        return "High"
    if product >= 18:
        return "Medium"
    return "Low"


def frontier_value(item: dict) -> float:
    p = PRIO_W[item["priority"]]
    i = IMPACT_W[item["scoring"]["impact_band"]]
    e = EV_CONF[item["evidence"]["strength"]]
    c = EFFORT_C[item["effort"]]
    return round(p * i * e / c, 2)


# --- loaders -------------------------------------------------------------------

def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def backlog_files() -> list[Path]:
    return sorted(BACKLOG_DIR.glob("QOS-*.yaml"))


def load_items() -> tuple[dict[str, dict], list[tuple[Path, str]]]:
    """Return ({id: item}, [(path, parse_error)])."""
    items: dict[str, dict] = {}
    errors: list[tuple[Path, str]] = []
    for path in backlog_files():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:  # pragma: no cover - defensive
            errors.append((path, f"YAML parse error: {exc}"))
            continue
        if not isinstance(data, dict):
            errors.append((path, "top-level YAML is not a mapping"))
            continue
        data["_path"] = path
        items[data.get("id", path.stem)] = data
    return items, errors


def load_journeys() -> list[dict]:
    if not JOURNEYS_PATH.exists():
        return []
    data = yaml.safe_load(JOURNEYS_PATH.read_text(encoding="utf-8")) or {}
    return data.get("journeys", [])


def open_items(items: dict[str, dict]) -> list[dict]:
    return [it for it in items.values() if it.get("lifecycle") in OPEN_STATES]


def strategy_gap_ids() -> list[str]:
    """Every G-<n> plus the two named gaps in docs/TESTING_STRATEGY.md."""
    if not STRATEGY_DOC.exists():
        return []
    text = STRATEGY_DOC.read_text(encoding="utf-8")
    ids = set(re.findall(r"\bG-\d+\b", text))
    for named in ("G-determinism", "G-mutation"):
        if named in text:
            ids.add(named)
    return sorted(ids, key=lambda s: (s.split("-")[1].isdigit() and int(s.split("-")[1]) or 999, s))
