#!/usr/bin/env python
"""Fail when the Task Register disagrees with the code.

    python qos/tools/register_drift.py [--register Bizboard_Product_Task_Universe_Master.xlsx] [--selftest]

Checks (exit 1 if any fails):

D1  A task marked ``Mechanism not found`` has a ``qos/register_claims.yaml`` entry with ``expect: absent``
    and its pattern now matches backend/ or web/src code -> the claim is stale (this is how S-0579,
    SEC-0624 and C-0603 went wrong).
D2  A task marked ``Code Complete & Verified`` / ``Validated (Supported)`` has an ``expect: present``
    entry whose pattern matches nothing -> a claim without code.
D3  ``Verification result`` is Pass but ``Test case ID`` or ``Last verified`` is empty.
D4  ``Test case ID`` names a test file that does not exist.
D5  ``Release gate`` is MVP, ``Work status`` is Gap, and no ``Decision`` is recorded on P0 gap decisions
    (reported as a warning, never fails the run).

The pattern file is deliberately small and human-written: add an entry whenever a row's status is a
claim about the code that could rot. Patterns are Python regexes, case-insensitive.
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

import openpyxl
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTER = REPO_ROOT / "Bizboard_Product_Task_Universe_Master.xlsx"
CLAIMS = REPO_ROOT / "qos" / "register_claims.yaml"
CODE_ROOTS = ("backend", "web/src")
SKIP_DIRS = {".venv", "node_modules", "migrations", "__pycache__", "tests", "dist", "media", "test_media"}
CODE_EXT = {".py", ".ts", ".tsx", ".js", ".jsx"}


def code_files(root: Path):
    for top in CODE_ROOTS:
        base = root / top
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if p.suffix in CODE_EXT and not (set(p.relative_to(root).parts) & SKIP_DIRS) and not p.name.startswith("test_"):
                yield p


_CORPUS: dict[Path, list[tuple[str, str]]] = {}


def _corpus(root: Path) -> list[tuple[str, str]]:
    """Read every code file once per run; patterns are then matched in memory."""
    if root not in _CORPUS:
        files = []
        for p in code_files(root):
            try:
                files.append((p.relative_to(root).as_posix(), p.read_text(encoding="utf-8", errors="ignore")))
            except OSError:
                pass
        _CORPUS[root] = files
    return _CORPUS[root]


def grep(pattern: str, root: Path) -> list[str]:
    rx = re.compile(pattern, re.I)
    return [rel for rel, text in _corpus(root) if rx.search(text)]


def load_rows(register: Path) -> list[dict]:
    ws = openpyxl.load_workbook(register, data_only=True)["Task Register"]
    head = [c.value for c in ws[1]]
    return [dict(zip(head, row)) for row in ws.iter_rows(min_row=2, values_only=True)]


def check(register: Path, claims_path: Path, root: Path) -> tuple[list[str], list[str]]:
    rows = {r["Task ID"]: r for r in load_rows(register)}
    claims = yaml.safe_load(claims_path.read_text(encoding="utf-8")) or []
    fails: list[str] = []
    warns: list[str] = []
    for c in claims:
        row = rows.get(c["task_id"])
        if row is None:
            fails.append(f"claims file names {c['task_id']} which is not in the register")
            continue
        status, hits = row.get("Validation Status"), grep(c["pattern"], root)
        if c["expect"] == "absent" and status == "Mechanism not found" and hits:
            fails.append(f"D1 {c['task_id']} is 'Mechanism not found' but /{c['pattern']}/ now matches {hits[:3]}")
        if c["expect"] == "present" and status in ("Code Complete & Verified", "Validated (Supported)") and not hits:
            fails.append(f"D2 {c['task_id']} is '{status}' but /{c['pattern']}/ matches no code")
    for tid, row in rows.items():
        refs = [t.strip() for t in str(row.get("Test case ID") or "").split(";") if t.strip()]
        if row.get("Verification result") == "Pass" and (not refs or not row.get("Last verified")):
            fails.append(f"D3 {tid} is Pass without a Test case ID and Last verified date")
        for ref in refs:
            f = ref.split("::")[0].strip()
            f = f if f.startswith(("backend/", "web/", "qos/")) else "backend/" + f
            if not (root / f).exists():
                fails.append(f"D4 {tid} names a test file that does not exist: {ref}")
        if row.get("Release gate") == "MVP" and row.get("Work status") == "Gap":
            warns.append(f"D5 {tid} is MVP and a Gap: decide before pilot")
    return fails, warns


def selftest() -> int:
    """Prove D1-D4 can fail, using a throwaway repo and register."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "backend" / "app").mkdir(parents=True)
        (root / "backend" / "app" / "mfa.py").write_text("def verify_totp(): pass\n")
        wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Task Register"
        ws.append(["Task ID", "Validation Status", "Test case ID", "Verification result", "Last verified", "Release gate", "Work status"])
        ws.append(["T-1", "Mechanism not found", None, None, None, "MVP", "Gap"])
        ws.append(["T-2", "Code Complete & Verified", None, None, None, "Pilot", "Built - unverified"])
        ws.append(["T-3", "Validated (Supported)", "tests/test_missing.py", "Pass", None, "Pilot", "Built - unverified"])
        reg = root / "r.xlsx"; wb.save(reg)
        cl = root / "claims.yaml"
        cl.write_text("- {task_id: T-1, expect: absent, pattern: 'verify_totp'}\n- {task_id: T-2, expect: present, pattern: 'no_such_symbol'}\n")
        fails, warns = check(reg, cl, root)
        kinds = {f.split()[0] for f in fails}
        ok = {"D1", "D2", "D3", "D4"} <= kinds and any(w.startswith("D5") for w in warns)
        print("selftest", "OK" if ok else f"FAILED: {fails}")
        return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--register", type=Path, default=DEFAULT_REGISTER)
    ap.add_argument("--claims", type=Path, default=CLAIMS)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.register.exists():
        print(f"register not found: {a.register}", file=sys.stderr)
        return 2
    fails, warns = check(a.register, a.claims, REPO_ROOT)
    for w in warns:
        print("warn ", w)
    for f in fails:
        print("FAIL ", f)
    print(f"{len(fails)} failure(s), {len(warns)} warning(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
