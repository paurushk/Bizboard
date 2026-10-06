#!/usr/bin/env python3
"""UX surface ledger (L1) generator and drift check.

Parses web/src/App.tsx routes, web/src/navigation/menu.ts and the page /
dialog files, then writes docs/ux/L1_surface_ledger.csv.

Human-maintained columns (status, load_score, notes, ...) are preserved when
the ledger is regenerated. With --check the script exits non-zero if a route,
page file or dialog is missing from the ledger.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web" / "src"
LEDGER = ROOT / "docs" / "ux" / "L1_surface_ledger.csv"

HUMAN_COLS = [
    "status", "journey", "heuristic_score", "cog_load_1to5", "choice_count",
    "axe_violations", "mobile_ok", "hi_parity", "notes", "phase",
]
AUTO_COLS = ["surface_id", "kind", "path", "component", "source_file", "guards", "nav_label", "has_test"]
COLS = AUTO_COLS + HUMAN_COLS

ROUTE_RE = re.compile(r'<Route\b([^>]*?)(/?)>')
PATH_RE = re.compile(r'\bpath="([^"]*)"')
ELEM_RE = re.compile(r'element=\{<(\w+)')
ALLOW_RE = re.compile(r'allow=\{([^}]+)\}')
LAZY_RE = re.compile(r"const (\w+) = lazy\(\(\) =>\s*import\('@/([^']+)'\)")
IMPORT_RE = re.compile(r"import \{([^}]+)\} from '@/([^']+)'")
NAV_RE = re.compile(r"id: '([^']+)',\s*labelKey: '([^']+)',\s*path: '([^']+)'")


def component_files(app_src: str) -> dict[str, str]:
    files: dict[str, str] = {}
    for name, rel in LAZY_RE.findall(app_src):
        files[name] = rel
    for names, rel in IMPORT_RE.findall(app_src):
        for n in (x.strip() for x in names.split(",")):
            files.setdefault(n, rel)
    return files


WRAP_RE = re.compile(r"^function (\w+)\(\)[^{]*\{(.*?)^\}", re.S | re.M)


def wrapper_targets(app_src: str, files: dict[str, str]) -> dict[str, list[str]]:
    """Locally defined route wrappers (e.g. SalesInvoiceEditor) -> page files they render."""
    out: dict[str, list[str]] = {}
    for name, body in WRAP_RE.findall(app_src):
        tgt = [files[c] for c in re.findall(r"<(\w+)", body) if c in files]
        if tgt:
            out[name] = tgt
    return out


def parse_routes(app_src: str, files: dict[str, str]) -> list[dict]:
    rows = []
    guards: list[str] = []  # stack aligned with open <Route> elements
    for line in app_src.splitlines():
        s = line.strip()
        if s.startswith("</Route>"):
            if guards:
                guards.pop()
            continue
        m = ROUTE_RE.search(s)
        if not m:
            continue
        attrs, selfclose = m.group(1), m.group(2)
        path = PATH_RE.search(attrs)
        elem = ELEM_RE.search(attrs)
        allow = ALLOW_RE.search(attrs)
        if elem and elem.group(1) == "RoleRoute" and allow and not path:
            guards.append(allow.group(1).strip())
            continue
        if not selfclose:
            guards.append("")
            if not path or not elem:
                continue
        is_index = bool(re.search(r"\bindex\b", attrs)) and not path
        if not path and not is_index:
            continue
        p = "/" + path.group(1).lstrip("/") if path else "/"
        comp = elem.group(1) if elem else ""
        kind = "redirect" if comp == "Navigate" else "page"
        rows.append({
            "kind": kind, "path": p, "component": comp,
            "source_file": files.get(comp, ""),
            "guards": "; ".join(g for g in guards if g),
        })
        if not selfclose and guards:
            guards.pop()
    return rows


def load_nav() -> dict[str, str]:
    src = (WEB / "navigation" / "menu.ts").read_text(encoding="utf-8")
    return {path: label for _id, label, path in NAV_RE.findall(src)}


def find_page_files() -> list[str]:
    out = []
    for p in (WEB / "pages").rglob("*.tsx"):
        if ".test." in p.name or p.name.startswith("_"):
            continue
        out.append(p.relative_to(WEB).as_posix())
    return sorted(out)


def find_dialogs() -> list[str]:
    out = []
    for p in WEB.rglob("*.tsx"):
        if ".test." in p.name:
            continue
        if re.search(r"(Dialog|Drawer|Modal|Wizard)", p.name):
            out.append(p.relative_to(WEB).as_posix())
    return sorted(out)


def imported_files() -> set[str]:
    """Files under src imported by any other non-test source file (so they are sub-components)."""
    hit: set[str] = set()
    pat = re.compile(r"""from ['"]((?:@/|\.{1,2}/)[^'"]+)['"]|import\(['"]((?:@/|\.{1,2}/)[^'"]+)['"]\)""")
    for p in WEB.rglob("*.ts*"):
        if ".test." in p.name or p.name == "App.tsx":
            continue
        for a, b in pat.findall(p.read_text(encoding="utf-8", errors="ignore")):
            spec = a or b
            base = (WEB / spec[2:]) if spec.startswith("@/") else (p.parent / spec)
            for suffix in (".tsx", ".ts", "/index.tsx"):
                cand = Path(str(base) + suffix)
                if cand.exists():
                    hit.add(cand.resolve().relative_to(WEB.resolve()).as_posix())
                    break
    return hit


def has_test(rel: str) -> str:
    if not rel:
        return ""
    base = WEB / rel
    for suffix in (".tsx", ".ts"):
        cand = base.with_suffix(".test" + suffix)
        if cand.exists():
            return "yes"
    if base.suffix == "":
        for suffix in (".tsx", ".ts"):
            if base.with_name(base.name + ".test" + suffix).exists():
                return "yes"
    return "no"


def resolve(rel: str) -> str:
    """Turn '@/pages/x/Y' into 'pages/x/Y.tsx' if the file exists."""
    if not rel:
        return ""
    for suffix in (".tsx", ".ts", "/index.tsx"):
        if (WEB / (rel + suffix)).exists():
            return rel + suffix
    return rel


def build() -> list[dict]:
    app_src = (WEB / "App.tsx").read_text(encoding="utf-8")
    files = component_files(app_src)
    wraps = wrapper_targets(app_src, files)
    nav = load_nav()
    rows = []
    seen_files = set()
    for r in parse_routes(app_src, files):
        if not r["source_file"] and r["component"] in wraps:
            r["source_file"] = ", ".join(resolve(t) for t in wraps[r["component"]])
            seen_files.update(resolve(t) for t in wraps[r["component"]])
        else:
            r["source_file"] = resolve(r["source_file"])
        r["nav_label"] = nav.get(r["path"], "")
        r["has_test"] = has_test(r["source_file"]) if r["kind"] == "page" else ""
        r["surface_id"] = f"R:{r['path']}:{r['component']}"
        if r["source_file"] and "," not in r["source_file"]:
            seen_files.add(r["source_file"])
        rows.append(r)
    imported = imported_files()
    for f in find_page_files():
        if f not in seen_files and f not in imported:
            rows.append({
                "surface_id": f"F:{f}", "kind": "page-file-unrouted", "path": "",
                "component": Path(f).stem, "source_file": f, "guards": "",
                "nav_label": "", "has_test": has_test(f),
            })
    for f in find_dialogs():
        rows.append({
            "surface_id": f"D:{f}", "kind": "dialog", "path": "",
            "component": Path(f).stem, "source_file": f, "guards": "",
            "nav_label": "", "has_test": has_test(f),
        })
    # de-dupe by id, keep first
    uniq, ids = [], set()
    for r in rows:
        if r["surface_id"] in ids:
            continue
        ids.add(r["surface_id"])
        uniq.append(r)
    return uniq


def read_ledger() -> dict[str, dict]:
    if not LEDGER.exists():
        return {}
    with LEDGER.open(newline="", encoding="utf-8") as fh:
        return {r["surface_id"]: r for r in csv.DictReader(fh)}


def main() -> int:
    check = "--check" in sys.argv
    rows = build()
    old = read_ledger()
    if check:
        missing = [r["surface_id"] for r in rows if r["surface_id"] not in old]
        stale = [k for k in old if k not in {r["surface_id"] for r in rows}]
        for m in missing:
            print(f"MISSING from ledger: {m}")
        for s in stale:
            print(f"STALE in ledger (surface gone): {s}")
        pending = [k for k, v in old.items() if v.get("status", "") in ("", "Pending")]
        print(f"{len(rows)} surfaces, {len(missing)} missing, {len(stale)} stale, {len(pending)} not yet audited")
        return 1 if (missing or stale) else 0
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            prev = old.get(r["surface_id"], {})
            out = {c: r.get(c, "") for c in AUTO_COLS}
            for c in HUMAN_COLS:
                out[c] = prev.get(c, "") or ("Pending" if c == "status" else "")
            w.writerow(out)
    print(f"wrote {len(rows)} surfaces to {LEDGER}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
