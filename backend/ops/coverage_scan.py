"""Deterministic repo scan feeding Coverage Copilot's LLM synthesis step.

Builds a structured JSON context (route x coverage-class x related open QOS
ids) from the actual repo tree — the LLM prioritizes/synthesizes this, it
doesn't have to build the inventory itself.

**Deployment note**: the backend Docker image's build context is
`./backend` only (see `docker-compose.yml`) — a deployed `api`/`worker`
container has no `web/`, `qos/`, or `docs/` on disk, only local dev (a full
repo checkout) does. `scan()` detects which case it's in: locally it scans
the live tree; in a container (or anywhere the sibling dirs are missing) it
falls back to the last snapshot written by `manage.py refresh_coverage_
snapshot` (run locally, output committed to `SNAPSHOT_PATH`), and is honest
in the result about which happened.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from django.conf import settings

SNAPSHOT_PATH = Path(__file__).resolve().parent / "data" / "coverage_snapshot.json"

_ROUTE_RE = re.compile(r'<Route\s+path="([^"]+)"')
_NAVIGATE_RE = re.compile(r'<Route\s+path="[^"]+"\s+element=\{<Navigate\b')
# Broad on purpose: a spec's route list is often a variable (route-smoke's
# `const ROUTES = [...]`, a11y's `for (const {path} of [...])`) rather than
# a literal argument to page.goto(...) — so this matches any quoted string
# that looks like an app path, anywhere in the file, not just call-site
# arguments. Over-matches a little (e.g. a path used only as an assertion
# comparison, not actually visited) in exchange for not silently missing
# whole files driven by a routes array.
_PATH_LITERAL_RE = re.compile(r"""['"`](/[a-zA-Z0-9_\-/:.]*)['"`]""")


def _repo_root() -> Path | None:
    candidate = Path(settings.BASE_DIR).parent
    if (candidate / "web").is_dir() and (candidate / "qos").is_dir():
        return candidate
    return None


def _scan_routes(repo_root: Path) -> list[str]:
    app_tsx = repo_root / "web" / "src" / "App.tsx"
    if not app_tsx.exists():
        return []
    text = app_tsx.read_text(encoding="utf-8", errors="replace")
    routes = []
    for line in text.splitlines():
        m = _ROUTE_RE.search(line)
        if not m or _NAVIGATE_RE.search(line):
            continue
        path = m.group(1)
        # Nested <Route path="sales/new"> entries omit the leading slash
        # (relative to their parent layout route) — normalize to the
        # absolute path an e2e spec actually navigates to.
        if not path.startswith("/"):
            path = "/" + path
        routes.append(path)
    return sorted(set(routes))


def _scan_spec_coverage(repo_root: Path, known_routes: set[str]) -> dict[str, list[str]]:
    """route -> list of spec files that reference it as a path literal."""
    coverage: dict[str, list[str]] = {}
    for base in ("web/e2e", "web/e2e-golden"):
        d = repo_root / base
        if not d.is_dir():
            continue
        for spec in d.rglob("*.spec.ts"):
            text = spec.read_text(encoding="utf-8", errors="replace")
            rel = str(spec.relative_to(repo_root)).replace("\\", "/")
            seen_in_file = set()
            for m in _PATH_LITERAL_RE.finditer(text):
                path = m.group(1).split("?")[0].rstrip("/") or "/"
                if path in known_routes and path not in seen_in_file:
                    seen_in_file.add(path)
                    coverage.setdefault(path, []).append(rel)
    return coverage


def _open_qos_items(repo_root: Path) -> list[dict]:
    import yaml

    backlog_dir = repo_root / "qos" / "backlog"
    if not backlog_dir.is_dir():
        return []
    open_states = {"open", "investigating", "in_progress"}
    items = []
    for f in sorted(backlog_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — a malformed item shouldn't sink the whole scan
            continue
        if not isinstance(data, dict) or data.get("lifecycle") not in open_states:
            continue
        items.append({
            "id": data.get("id"),
            "title": data.get("title"),
            "priority": data.get("priority"),
            "effort": data.get("effort"),
        })
    return items


def _g_register_excerpt(repo_root: Path) -> str:
    doc = repo_root / "docs" / "TESTING_STRATEGY.md"
    if not doc.exists():
        return ""
    text = doc.read_text(encoding="utf-8", errors="replace")
    lines = [ln for ln in text.splitlines() if re.match(r"^\|\s*\*\*G-\d+[a-z]?\*\*", ln)]
    return "\n".join(lines)


def scan() -> dict:
    repo_root = _repo_root()
    if repo_root is None:
        if SNAPSHOT_PATH.exists():
            snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
            snapshot["source"] = "snapshot"
            return snapshot
        return {
            "source": "unavailable",
            "note": (
                "No live repo tree (this is a deployed container — only "
                "backend/ is baked in) and no committed snapshot at "
                f"{SNAPSHOT_PATH}. Run `python manage.py "
                "refresh_coverage_snapshot` locally and commit the result."
            ),
            "routes": [],
            "route_coverage": {},
            "open_qos_items": [],
            "g_register": "",
        }

    routes = _scan_routes(repo_root)
    spec_coverage = _scan_spec_coverage(repo_root, known_routes=set(routes))
    route_coverage = {}
    for route in routes:
        specs = spec_coverage.get(route, [])
        non_smoke_specs = [s for s in specs if "route-smoke.spec.ts" not in s]
        if non_smoke_specs:
            route_coverage[route] = {"class": "flow", "specs": specs}
        elif specs:
            # only route-smoke.spec.ts touches this route: render-check only.
            route_coverage[route] = {"class": "smoke", "specs": specs}
        else:
            route_coverage[route] = {"class": "none", "specs": []}

    return {
        "source": "live_scan",
        "routes": routes,
        "route_coverage": route_coverage,
        "open_qos_items": _open_qos_items(repo_root),
        "g_register": _g_register_excerpt(repo_root),
    }
