#!/usr/bin/env python3
"""UX programme Phase 1: static cognitive-load and UX-signal scan of every routed page.

Reads docs/ux/L1_surface_ledger.csv, follows first-degree local imports of each
page, and counts controls and UX-relevant signals. Writes docs/ux/static_scan.csv
and fills the choice_count / cog_load_1to5 columns of the ledger.

The score is a triage heuristic, not a measurement. It ranks screens for the
manual walkthrough and the NASA-TLX-lite sessions.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web" / "src"
LEDGER = ROOT / "docs" / "ux" / "L1_surface_ledger.csv"
OUT = ROOT / "docs" / "ux" / "static_scan.csv"

IMPORT_RE = re.compile(r"""from ['"]((?:@/|\./|\.\./)[^'"]+)['"]""")

FIELD_RE = re.compile(r"<(TextField|Autocomplete|Select|NumericField|DatePicker|DateField|Checkbox|Switch|RadioGroup|FormControlLabel|MoneyField|PartyPicker|ProductPicker)\b")
BUTTON_RE = re.compile(r"<(Button|LoadingButton|Fab|Link|MenuItem)\b")
ICONBTN_RE = re.compile(r"<IconButton\b([^>]*)>", re.S)
TAB_RE = re.compile(r"<Tab\b")
DIALOG_RE = re.compile(r"<(Dialog|Drawer|Popover|Menu)\b")
STEP_RE = re.compile(r"<Step\b")
T_CALL_RE = re.compile(r"\bt\(\s*['\"`]")
# Visible hard-coded English in JSX text nodes and common string props.
JSX_TEXT_RE = re.compile(r">\s*([A-Z][A-Za-z][A-Za-z ,.'&/-]{3,60})\s*<")
PROP_TEXT_RE = re.compile(r"\b(label|placeholder|title|helperText|aria-label)=\"([A-Z][^\"]{3,60})\"")
LOADING_RE = re.compile(r"Skeleton|CircularProgress|LinearProgress|isLoading|isPending|isFetching")
ERROR_RE = re.compile(r"isError|<Alert\b|error\.message|HelpErrorAlert|ErrorState")
EMPTY_RE = re.compile(r"EmptyState|NoRows|noRows|\.length === 0|isEmpty|no[A-Z]\w+Found|emptyText", re.I)
RESP_RE = re.compile(r"useMediaQuery|breakpoints\.(down|up)|xs:\s*|\bsm:\s*|\bmd:\s*")
GUARD_RE = re.compile(r"UnsavedChangesGuard|useUnsavedChanges|deviceDraft")
CONFIRM_RE = re.compile(r"ConfirmDialog|window\.confirm|confirm\(")
ARIA_LIVE_RE = re.compile(r"aria-live|role=\"alert\"|role=\"status\"")
TESTID_RE = re.compile(r"data-testid")
ONCLICK_DIV_RE = re.compile(r"<(div|span|td|tr)\b[^>]*\bonClick=")
SIZE_SMALL_RE = re.compile(r"size=\"small\"")
TABLE_RE = re.compile(r"<(Table|DataGrid|VirtualizedTable)\b")
FILTER_RE = re.compile(r"filter|Filter|search|Search")


def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def resolve_import(spec: str, base: Path) -> Path | None:
    root = (WEB / spec[2:]) if spec.startswith("@/") else (base.parent / spec)
    for suffix in (".tsx", ".ts", "/index.tsx"):
        cand = Path(str(root) + suffix)
        if cand.exists():
            return cand
    return None


def gather(src: Path) -> list[Path]:
    """Page file plus first-degree local imports that are UI (pages/, components/)."""
    files = [src]
    for spec in IMPORT_RE.findall(read(src)):
        p = resolve_import(spec, src)
        if not p:
            continue
        rel = p.resolve().relative_to(WEB.resolve()).as_posix()
        if (rel.startswith("pages/") or rel.startswith("components/")) and ".test." not in rel and p.suffix == ".tsx":
            if p not in files:
                files.append(p)
    return files


def scan(files: list[Path]) -> dict:
    text = "\n".join(read(f) for f in files)
    loc = text.count("\n")
    icon_missing = sum(1 for m in ICONBTN_RE.finditer(text) if "aria-label" not in m.group(1) and "title=" not in m.group(1))
    hard = {m.group(1) for m in JSX_TEXT_RE.finditer(text)} | {m.group(2) for m in PROP_TEXT_RE.finditer(text)}
    hard = {h for h in hard if not re.match(r"^[A-Z]{2,}\b", h) and " " in h or len(h) > 7}
    fields = len(FIELD_RE.findall(text))
    buttons = len(BUTTON_RE.findall(text)) + len(ICONBTN_RE.findall(text))
    tabs = len(TAB_RE.findall(text))
    dialogs = len(DIALOG_RE.findall(text))
    steps = len(STEP_RE.findall(text))
    choice = fields + buttons + tabs
    # Triage score 1-5 (see docstring): concepts on screen weighted by how much they ask of the user.
    raw = fields * 1.0 + buttons * 0.6 + tabs * 1.5 + dialogs * 1.0 + steps * 1.0
    score = 1 if raw < 8 else 2 if raw < 18 else 3 if raw < 32 else 4 if raw < 55 else 5
    return {
        "files": len(files),
        "loc": loc,
        "fields": fields,
        "buttons": buttons,
        "tabs": tabs,
        "dialogs": dialogs,
        "steps": steps,
        "choice_count": choice,
        "cog_load_1to5": score,
        "t_calls": len(T_CALL_RE.findall(text)),
        "hardcoded_strings": len(hard),
        "hardcoded_sample": " | ".join(sorted(hard)[:3]),
        "iconbtn_no_label": icon_missing,
        "div_onclick": len(ONCLICK_DIV_RE.findall(text)),
        "small_controls": len(SIZE_SMALL_RE.findall(text)),
        "has_loading": int(bool(LOADING_RE.search(text))),
        "has_error": int(bool(ERROR_RE.search(text))),
        "has_empty": int(bool(EMPTY_RE.search(text))),
        "has_responsive": int(bool(RESP_RE.search(text))),
        "has_guard": int(bool(GUARD_RE.search(text))),
        "has_confirm": int(bool(CONFIRM_RE.search(text))),
        "has_live_region": int(bool(ARIA_LIVE_RE.search(text))),
        "has_table": int(bool(TABLE_RE.search(text))),
        "has_filter": int(bool(FILTER_RE.search(text))),
    }


def main() -> None:
    with LEDGER.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
        fieldnames = list(rows[0].keys())
    out_rows = []
    cache: dict[str, dict] = {}
    for r in rows:
        if r["kind"] not in ("page", "dialog") or not r["source_file"]:
            continue
        srcs = [s.strip() for s in r["source_file"].split(",") if s.strip()]
        files: list[Path] = []
        for s in srcs:
            p = WEB / s
            if p.exists():
                files.extend(f for f in gather(p) if f not in files)
        if not files:
            continue
        key = "|".join(str(f) for f in files)
        if key not in cache:
            cache[key] = scan(files)
        m = cache[key]
        r["choice_count"] = str(m["choice_count"])
        r["cog_load_1to5"] = str(m["cog_load_1to5"])
        out_rows.append({"surface_id": r["surface_id"], "path": r["path"], "component": r["component"], **m})
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    with LEDGER.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"scanned {len(out_rows)} surfaces -> {OUT}")


if __name__ == "__main__":
    main()
