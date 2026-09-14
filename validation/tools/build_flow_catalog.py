"""Compute coverage labels and render docs/FLOW_CATALOG.md.

Heuristic first pass (P1-T4): goldens → JOURNEY, e2e smoke → SMOKE,
persona/workflow tests → API-ONLY, freeze §B → OUT, B7-style → LIM,
no A-row → UNMAPPED, else GAP. Human fields in overrides.yaml win per
field (qos/tools/merge.py pattern).

P1-T5 joins list-valued personas/archetypes from freeze_route_map.yaml
(longest prefix wins). P1-T6: HOLISTIC_VALIDATION_REVIEW.md §2 is frozen;
this generated doc is the live inventory.

    python validation/tools/build_flow_catalog.py
    python validation/tools/build_flow_catalog.py --selftest
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

import jsonschema

from _common import (
    FLOW_DOC,
    FLOW_ITEM_SCHEMA,
    FLOW_ITEMS_YAML,
    FREEZE_MAP_YAML,
    OVERRIDES_PATH,
    REPO_ROOT,
    dump_yaml,
    load_json,
    load_yaml,
    normalize_path,
)
from extract_actions import load_actions, validate_actions
from extract_routes import build_from_files, write_catalog

_GOLDEN_DIR = REPO_ROOT / "web" / "e2e-golden"
_E2E_DIR = REPO_ROOT / "web" / "e2e"
_PERSONA_DIR = REPO_ROOT / "backend" / "tests" / "personas"
_WORKFLOW_DIR = REPO_ROOT / "backend" / "tests" / "workflows"

_GROUP_ORDER = [
    ("public", "Public / unauthenticated"),
    ("first_run", "First-run / home / attention"),
    ("pos", "POS"),
    ("sales", "Sales"),
    ("purchases", "Purchases"),
    ("payments", "Payments"),
    ("inventory", "Inventory"),
    ("reports", "Reports"),
    ("insights", "Insights"),
    ("accounting", "Accounting"),
    ("settings", "Settings"),
    ("dark", "Dark modules"),
    ("other", "Other"),
    ("actions", "In-page actions"),
]


def _join_for(path: str, fmap: dict) -> tuple[list[str], list[str]]:
    """P1-T5: list-valued personas/archetypes. Longest prefix wins."""
    defaults = fmap.get("default_join") or {}
    personas = list(defaults.get("personas") or ["P1"])
    archetypes = list(defaults.get("archetypes") or ["ARCH-01"])
    best = ""
    best_row = None
    for prefix, row in (fmap.get("persona_prefixes") or {}).items():
        p = normalize_path(str(prefix))
        if path == p:
            matched = True
        elif p != "/" and (path.startswith(p + "/") or path.startswith(p + ":")):
            matched = True
        else:
            matched = False
        if matched and len(p) >= len(best):
            best = p
            best_row = row or {}
    if best_row:
        personas = list(best_row.get("personas") or personas)
        archetypes = list(best_row.get("archetypes") or archetypes)
    return personas, archetypes


def _read_corpus(paths: list[Path]) -> str:
    chunks: list[str] = []
    for p in paths:
        if not p.exists():
            continue
        if p.is_file():
            try:
                chunks.append(p.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
            continue
        for f in p.rglob("*"):
            if f.suffix.lower() in {".ts", ".tsx", ".py", ".js"}:
                try:
                    chunks.append(f.read_text(encoding="utf-8", errors="ignore"))
                except OSError:
                    continue
    return "\n".join(chunks)


def _path_mentioned(corpus: str, path: str) -> bool:
    if path == "/":
        # Too many false positives; only count explicit goto('/') / toHaveURL('/')
        return bool(re.search(r"""(?:goto|toHaveURL|path:\s*)\(\s*['\"]\/['\"]""", corpus))
    variants = {path}
    if path.startswith("/"):
        variants.add(path.lstrip("/"))
    for v in variants:
        if v in corpus:
            return True
    return False


def _longest_prefix(path: str, prefixes: list[str]) -> str | None:
    hits: list[str] = []
    for p in prefixes:
        if path == p:
            hits.append(p)
        elif p != "/" and (
            path.startswith(p + "/")
            or (path.startswith(p) and len(path) > len(p) and path[len(p)] in "/:")
        ):
            hits.append(p)
    return max(hits, key=len) if hits else None


def _freeze_for(path: str, fmap: dict) -> dict:
    out_prefixes = list(fmap.get("out_prefixes") or [])
    lim_exact = set(fmap.get("lim_exact") or [])
    defects = set(fmap.get("known_defect_not_gated") or [])
    a_rows = dict(fmap.get("a_rows") or {})
    out_hit = _longest_prefix(path, out_prefixes)
    a_hit = None
    if path in a_rows:
        a_hit = a_rows[path]
    else:
        pref = _longest_prefix(path, list(a_rows.keys()))
        if pref:
            a_hit = a_rows[pref]
    rec = {
        "out": bool(out_hit),
        "lim": path in lim_exact,
        "a_row": a_hit,
        "defect": "known-defect-not-gated" if path in defects else None,
    }
    return rec


def _coverage_for_route(
    path: str,
    route_kind: str,
    freeze: dict,
    golden: str,
    e2e: str,
    api: str,
    smoke_paths: set[str],
) -> tuple[str, list[str]]:
    evidence: list[str] = []
    if route_kind == "redirect":
        if freeze["out"]:
            evidence = ["redirect — dark alias"]
            if freeze["defect"]:
                evidence.append(freeze["defect"])
            return "OUT", evidence
        return "LIM", ["redirect — not a page"]
    if freeze["out"]:
        evidence.append("FREEZE_SCOPE §B / dark prefix")
        if freeze["defect"]:
            evidence.append(freeze["defect"])
        return "OUT", evidence
    if freeze["lim"]:
        evidence.append("LIM — reachable, not freeze-journeyed")
        return "LIM", evidence
    if _path_mentioned(golden, path):
        evidence.append("e2e-golden")
        label = "JOURNEY"
    elif path in smoke_paths or _path_mentioned(e2e, path):
        evidence.append("e2e smoke / domain spec; no business-outcome assertion")
        label = "SMOKE"
    elif _path_mentioned(api, path):
        evidence.append("persona/workflow API test")
        label = "API-ONLY"
    else:
        label = None
    if not freeze["a_row"]:
        evidence.append("no FREEZE_SCOPE A-row")
        return "UNMAPPED", evidence
    if label:
        return label, evidence
    evidence.append(f"mapped {freeze['a_row']}, no gating UI/API test found")
    return "GAP", evidence


def apply_overrides(item: dict, overrides: dict) -> dict:
    if not overrides:
        return item
    patch = (overrides.get("routes") or {}).get(item["path"]) if item["kind"] == "route" else (overrides.get("actions") or {}).get(item["path"])
    if not patch:
        return item
    out = dict(item)
    for key, val in patch.items():
        if key == "note":
            ev = list(out.get("coverage_evidence") or [])
            ev.append(f"override: {val}")
            out["coverage_evidence"] = ev
            continue
        out[key] = val
    out["override"] = True
    return out


def group_for(path: str, kind: str) -> str:
    if kind == "action":
        return "actions"
    if path in ("/login", "/register", "/forgot-password", "/reset-password", "/invite", "/pay/:token") or path.startswith("/pay/"):
        return "public"
    if path in ("/", "/setup", "/attention", "/help"):
        return "first_run"
    if path == "/pos" or path.startswith("/pos/"):
        return "pos"
    if path.startswith("/sales/"):
        return "sales"
    if path.startswith("/purchases/"):
        return "purchases"
    if path.startswith("/payments/"):
        return "payments"
    if path.startswith("/inventory/"):
        return "inventory"
    if path.startswith("/reports/") or path == "/ca-needs":
        return "reports"
    if path.startswith("/insights"):
        return "insights"
    if path.startswith("/accounting/"):
        return "accounting"
    if path.startswith("/settings/"):
        return "settings"
    if any(path.startswith(p) for p in ("/manufacturing", "/payroll", "/crm")):
        return "dark"
    return "other"


def build_items(result: dict | None = None) -> list[dict]:
    if result is None:
        result = build_from_files()
        write_catalog(result)
    fmap = load_yaml(FREEZE_MAP_YAML) or {}
    overrides = load_yaml(OVERRIDES_PATH) or {}
    golden = _read_corpus([_GOLDEN_DIR])
    e2e = _read_corpus([_E2E_DIR])
    api = _read_corpus([_PERSONA_DIR, _WORKFLOW_DIR])
    smoke_paths = {normalize_path(p) for p in result.get("smoke_paths") or []}
    items: list[dict] = []
    for r in result["routes"]:
        freeze = _freeze_for(r["path"], fmap)
        personas, archetypes = _join_for(r["path"], fmap)
        coverage, evidence = _coverage_for_route(
            r["path"], r["route_kind"], freeze, golden, e2e, api, smoke_paths,
        )
        item = {
            "path": r["path"],
            "kind": "route",
            "route_kind": r["route_kind"],
            "component": r.get("component") or "",
            "guards": r.get("guards") or [],
            "redirect_to": r.get("redirect_to"),
            "nav_label": r.get("nav_label"),
            "coverage": coverage,
            "coverage_evidence": evidence,
            "freeze_row": freeze["a_row"],
            "defect": freeze["defect"],
            "personas": personas,
            "archetypes": archetypes,
            "override": False,
        }
        if item["redirect_to"] is None:
            item.pop("redirect_to", None)
        items.append(apply_overrides(item, overrides))

    for action in load_actions():
        item = {
            "path": action["id"],
            "kind": "action",
            "route_kind": "action",
            "component": action["title"],
            "guards": [],
            "nav_label": None,
            "coverage": "GAP",
            "coverage_evidence": [action.get("review_row") or "§2.13"],
            "freeze_row": None,
            "defect": None,
            "personas": ["P1"],
            "archetypes": ["ARCH-01", "ARCH-03"],
            "override": False,
        }
        items.append(apply_overrides(item, overrides))
    return items


def validate_items(items: list[dict]) -> list[str]:
    schema = load_json(FLOW_ITEM_SCHEMA)
    v = jsonschema.Draft202012Validator(schema)
    errors: list[str] = []
    for it in items:
        payload = {k: val for k, val in it.items() if val is not None}
        # schema forbids extra; drop empty optional lists if needed
        for e in sorted(v.iter_errors(payload), key=str):
            loc = "/".join(str(p) for p in e.path) or "(root)"
            errors.append(f"{it.get('path')}: {loc}: {e.message}")
    return errors


def render_markdown(items: list[dict], route_count: int, dead_nav: list[str]) -> str:
    counts = Counter(it["coverage"] for it in items if it["kind"] == "route" and it["route_kind"] != "redirect")
    pages = [it for it in items if it["kind"] == "route" and it["route_kind"] != "redirect"]
    lines = [
        "# Flow catalog (Graph 1)",
        "",
        "> GENERATED by `validation/tools/build_flow_catalog.py` — **do not hand-edit**. "
        "Correct labels in `validation/overrides.yaml`. Source routes: `web/src/App.tsx`. "
        "`HOLISTIC_VALIDATION_REVIEW.md` §2 is frozen (P1-T6); this file is the live inventory.",
        "",
        f"Router pages+index: **{len(pages)}**. All extracted routes (incl. redirects): **{route_count}**.",
        "",
        "| Label | Count |",
        "|---|---:|",
    ]
    for label in ("JOURNEY", "API-ONLY", "SMOKE", "GAP", "OUT", "LIM", "UNMAPPED", "FLAG-OFF", "UNIT"):
        lines.append(f"| {label} | {counts.get(label, 0)} |")
    lines += [
        "",
        "Coverage is heuristic. `UNMAPPED` means no FREEZE_SCOPE.md A-row — expected on day one. "
        "`SMOKE` means a crash-only e2e/domain spec exists (no business-outcome assertion) — "
        "still a gap, not a pass. `LIM` means FREEZE_SCOPE.md itself marks the route "
        "reachable-but-not-journey-worthy (e.g. B7-style out-of-freeze features) — do not use it "
        "for 'has some test coverage.' `OUT` is dark / NOT SUPPORTED.",
        "",
    ]
    if dead_nav:
        lines += ["## Nav mismatches (`menu.ts` path with no router entry)", "", "| Path |", "|---|"]
        for d in dead_nav:
            lines.append(f"| `{d}` |")
        lines.append("")

    grouped: dict[str, list[dict]] = {k: [] for k, _ in _GROUP_ORDER}
    for it in items:
        grouped.setdefault(group_for(it["path"], it["kind"]), []).append(it)

    for key, title in _GROUP_ORDER:
        rows = grouped.get(key) or []
        if not rows:
            continue
        lines += [f"## {title}", "", "| Path | Kind | Coverage | Freeze | Personas | Archetypes | Evidence |", "|---|---|---|---|---|---|---|"]
        for it in sorted(rows, key=lambda x: x["path"]):
            ev = "; ".join(it.get("coverage_evidence") or [])
            freeze = it.get("freeze_row") or it.get("defect") or ""
            personas = ", ".join(it.get("personas") or [])
            archetypes = ", ".join(it.get("archetypes") or [])
            lines.append(
                f"| `{it['path']}` | {it['route_kind']} | **{it['coverage']}** | {freeze} | {personas} | {archetypes} | {ev} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def write_outputs(items: list[dict], result: dict) -> None:
    dump_yaml({"items": items}, FLOW_ITEMS_YAML)
    FLOW_DOC.write_text(render_markdown(items, result["count"], result.get("dead_nav") or []), encoding="utf-8")


def _selftest() -> int:
    # Override merge: generated JOURNEY + override coverage GAP keeps other fields.
    generated = {
        "path": "/sales/quick-entry",
        "kind": "route",
        "route_kind": "page",
        "coverage": "UNMAPPED",
        "coverage_evidence": ["no A-row"],
        "override": False,
    }
    merged = apply_overrides(generated, {"routes": {"/sales/quick-entry": {"coverage": "GAP", "note": "x"}}})
    if merged["coverage"] != "GAP" or not merged["override"]:
        print(f"FAIL override merge: {merged}")
        return 1
    print("ok    overrides.yaml merge is non-destructive per field")
    freeze = _freeze_for("/purchases/bills-of-entry", load_yaml(FREEZE_MAP_YAML) or {})
    if not freeze["out"] or freeze["defect"] != "known-defect-not-gated":
        print(f"FAIL BoE freeze map: {freeze}")
        return 1
    print("ok    BoE is OUT + known-defect-not-gated")
    freeze_rec = _freeze_for("/sales/recurring", load_yaml(FREEZE_MAP_YAML) or {})
    if not freeze_rec["lim"]:
        print(f"FAIL recurring LIM: {freeze_rec}")
        return 1
    print("ok    /sales/recurring is LIM")
    pos_p, pos_a = _join_for("/pos", load_yaml(FREEZE_MAP_YAML) or {})
    if "P2" not in pos_p or "ARCH-01" not in pos_a:
        print(f"FAIL pos join: {pos_p} {pos_a}")
        return 1
    print("ok    /pos joins P2 + ARCH-01 (list-valued)")
    empty_freeze = {"out": False, "lim": False, "a_row": None, "defect": None}
    cov, ev = _coverage_for_route("/sales/challans", "redirect", empty_freeze, "", "", "", set())
    if cov != "LIM":
        print(f"FAIL redirect LIM: {cov} {ev}")
        return 1
    print("ok    non-dark redirect is LIM (not a page)")
    fmap = load_yaml(FREEZE_MAP_YAML) or {}
    crm_freeze = _freeze_for("/crm", fmap)
    cov, ev = _coverage_for_route("/crm", "redirect", crm_freeze, "", "", "", set())
    if cov != "OUT":
        print(f"FAIL dark redirect OUT: {cov} {ev}")
        return 1
    print("ok    /crm redirect is OUT")
    page_freeze = {"out": False, "lim": False, "a_row": "A16", "defect": None}
    cov, ev = _coverage_for_route(
        "/settings/backup", "page", page_freeze, "", "goto('/settings/backup')", "", set()
    )
    if cov != "SMOKE":
        print(f"FAIL smoke-only freeze page SMOKE: {cov} {ev}")
        return 1
    print("ok    presence-only freeze page is SMOKE, not LIM (crash-only != acceptable-gap)")
    cov, ev = _coverage_for_route(
        "/sales/history", "page", {"out": False, "lim": False, "a_row": "A1", "defect": None},
        "goto('/sales/history')", "", "", set(),
    )
    if cov != "JOURNEY":
        print(f"FAIL golden still JOURNEY: {cov} {ev}")
        return 1
    print("ok    e2e-golden mention stays JOURNEY")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()

    action_errs = validate_actions(load_actions())
    if action_errs:
        print("actions.yaml invalid:")
        for e in action_errs:
            print(f"  {e}")
        return 1

    result = build_from_files()
    if result["errors"]:
        print("extract_routes errors:")
        for e in result["errors"]:
            print(f"  {e}")
        return 1
    write_catalog(result)
    items = build_items(result)
    schema_errs = validate_items(items)
    if schema_errs:
        print("flow item schema:")
        for e in schema_errs[:20]:
            print(f"  {e}")
        if len(schema_errs) > 20:
            print(f"  ... {len(schema_errs) - 20} more")
        return 1
    write_outputs(items, result)
    pages = [i for i in items if i["kind"] == "route" and i["route_kind"] != "redirect"]
    print(f"wrote {FLOW_DOC} ({len(pages)} pages, {result['count']} extracted routes, {len(load_actions())} actions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
