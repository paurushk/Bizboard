"""Shared helpers for Graph 1 validation tools.

Mirrors qos/tools/_common.py: no framework, paths relative to repo root.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATION_DIR = REPO_ROOT / "validation"
SCHEMA_DIR = VALIDATION_DIR / "schema"
CATALOG_DIR = VALIDATION_DIR / "catalog"
OVERRIDES_PATH = VALIDATION_DIR / "overrides.yaml"
FLOW_DOC = REPO_ROOT / "docs" / "FLOW_CATALOG.md"
APP_TSX = REPO_ROOT / "web" / "src" / "App.tsx"
MENU_TS = REPO_ROOT / "web" / "src" / "navigation" / "menu.ts"
PROTECTED_ROUTES_TS = REPO_ROOT / "web" / "e2e" / "helpers" / "protectedRoutes.ts"
FLOW_ITEM_SCHEMA = SCHEMA_DIR / "flow_item.schema.json"
ACTION_SCHEMA = SCHEMA_DIR / "action_item.schema.json"
ACTIONS_YAML = CATALOG_DIR / "actions.yaml"
ROUTES_YAML = CATALOG_DIR / "routes.yaml"
FLOW_ITEMS_YAML = CATALOG_DIR / "flow_items.yaml"
ROUTE_COUNT_JSON = CATALOG_DIR / "route_count.json"
FREEZE_MAP_YAML = CATALOG_DIR / "freeze_route_map.yaml"
EVENTS_YAML = CATALOG_DIR / "events.yaml"
EVENT_SCHEMA = SCHEMA_DIR / "event.schema.json"
EVENT_MATRIX_YAML = CATALOG_DIR / "event_matrix.yaml"
EVENT_DOC = REPO_ROOT / "docs" / "EVENT_MATRIX.md"
CROSS_FLOW_DOC = REPO_ROOT / "docs" / "CROSS_FLOW_IMPACT_MAP.md"

COVERAGE_LABELS = (
    "JOURNEY", "API-ONLY", "SMOKE", "FLAG-OFF", "UNIT",
    "GAP", "OUT", "LIM", "UNMAPPED",
)


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def dump_yaml(data, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(data, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def normalize_path(path: str) -> str:
    if not path:
        return "/"
    if not path.startswith("/"):
        path = "/" + path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return path
