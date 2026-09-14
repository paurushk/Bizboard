"""Advisory: a money/stock writer diff needs a test path or an explicit skip (P2-T6).

A PR that changes sales/purchases/payments/inventory/accounting/ledgers write
paths must also change a test (backend/tests, web/e2e-golden) OR include a
`validation-impact: none` reason file. Advisory until Phase 6 flip (A3 calendar
does not apply here — this gate flips with Phase 6, not the 2-week catalog rule).
"""

from __future__ import annotations

import sys
from pathlib import Path

NAME = "writer_impact_coverage"
CONSEQUENCE = (
    "A money/stock writer changed without a test path or "
    "`validation-impact: none` reason — Graph 2 coverage can silently decay."
)
ADVISORY = True

_WRITER_PREFIXES = (
    "backend/sales/",
    "backend/purchases/",
    "backend/payments/",
    "backend/inventory/",
    "backend/accounting/",
    "backend/ledgers/",
)
_TEST_PREFIXES = (
    "backend/tests/",
    "web/e2e-golden/",
    "web/e2e/",
    "backend/core/invariants/",
)
_SKIP_PARTS = ("migrations",)


def _is_writer(path: str) -> bool:
    if not path.endswith(".py"):
        return False
    if any(f"/{p}/" in f"/{path}/" for p in _SKIP_PARTS):
        return False
    return any(path.startswith(p) for p in _WRITER_PREFIXES)


def _is_test(path: str) -> bool:
    return any(path.startswith(p) for p in _TEST_PREFIXES)


def _changed_files(root: Path) -> list[str]:
    manifest = root / "validation" / "catalog" / "changed_files.txt"
    if manifest.exists():
        return [ln.strip().replace("\\", "/") for ln in manifest.read_text(encoding="utf-8").splitlines() if ln.strip()]
    import subprocess

    for base in ("origin/main", "main"):
        proc = subprocess.run(
            ["git", "diff", "--name-only", f"{base}...HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            return [ln.strip().replace("\\", "/") for ln in proc.stdout.splitlines() if ln.strip()]
    return []


def _has_skip_reason(root: Path, changed: list[str]) -> bool:
    skip = root / "validation" / "impact-none.txt"
    if skip.exists() and skip.read_text(encoding="utf-8").strip():
        return True
    for path in changed:
        if path.lower().endswith("validation-impact.md"):
            return True
    return False


def check(root: Path) -> list[str]:
    changed = _changed_files(root)
    writers = [p for p in changed if _is_writer(p)]
    if not writers:
        return []
    if any(_is_test(p) for p in changed):
        return []
    if _has_skip_reason(root, changed):
        return []
    listed = ", ".join(writers[:8])
    extra = f" (+{len(writers) - 8} more)" if len(writers) > 8 else ""
    return [
        f"writer files changed without tests or `validation/impact-none.txt`: {listed}{extra}"
    ]


def make_bad_tree(root: Path) -> None:
    sales = root / "backend" / "sales"
    sales.mkdir(parents=True)
    (sales / "services.py").write_text("def complete():\n    return None\n", encoding="utf-8")
    manifest = root / "validation" / "catalog"
    manifest.mkdir(parents=True)
    (manifest / "changed_files.txt").write_text("backend/sales/services.py\n", encoding="utf-8")


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[3]
    out = check(root)
    if out:
        print(f"GUARD FAIL {NAME}:")
        for v in out:
            print("  ", v)
        sys.exit(1)
    print(f"GUARD OK {NAME}")
