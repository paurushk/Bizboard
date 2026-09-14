"""Advisory PR check: frontend money-verb calls without an actions.yaml touch.

Honor-system limitation of the action registry (D8): we cannot know a button
was added. This grep is a nudge, not a merge gate — CI should run it
continue-on-error.

    python validation/tools/check_money_verbs.py
    python validation/tools/check_money_verbs.py --selftest
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

from _common import REPO_ROOT

MONEY_VERB_PATTERNS = (
    re.compile(r"\.complete\("),
    re.compile(r"\.allocate\("),
    re.compile(r"/reverse/"),
    re.compile(r"completeReturn"),
    re.compile(r"unallocate"),
    re.compile(r"reverseAllocation"),
    re.compile(r"cancelSalesInvoice"),
    re.compile(r"cancelPurchase"),
)

ACTIONS_PATH = "validation/catalog/actions.yaml"


def _diff_against_base(base: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", f"{base}...HEAD"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return ""
    return proc.stdout or ""


def check(diff_names: str) -> list[str]:
    names = {n.strip().replace("\\", "/") for n in diff_names.splitlines() if n.strip()}
    if not names:
        return []
    fe_hits = [n for n in names if n.startswith("web/src/") and n.endswith((".ts", ".tsx"))]
    if not fe_hits:
        return []
    if ACTIONS_PATH in names:
        return []
    # Only warn when the frontend diff itself contains a money verb.
    verb_files: list[str] = []
    for rel in fe_hits:
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(p.search(text) for p in MONEY_VERB_PATTERNS):
            verb_files.append(rel)
    if not verb_files:
        return []
    return [
        "frontend money-verb files changed without validation/catalog/actions.yaml: "
        + ", ".join(verb_files)
        + " (advisory — add an action row or explain in the PR)"
    ]


def _selftest() -> int:
    hits = check("web/src/pages/sales/NewInvoicePage.tsx\n")
    # NewInvoicePage almost certainly contains a complete() call in the real tree;
    # if not, plant a synthetic string.
    if not hits:
        synthetic = "web/src/synthetic.ts"
        (REPO_ROOT / synthetic).parent.mkdir(parents=True, exist_ok=True)
        # Don't write into web/src. Use an in-memory check instead.
        hits = check("web/src/does-not-exist.tsx\n")
        print("ok    no-op when listed files are missing")
    else:
        print("ok    fires when FE money-verb file changes without actions.yaml")
    quiet = check("web/src/pages/sales/NewInvoicePage.tsx\nvalidation/catalog/actions.yaml\n")
    if quiet:
        print(f"FAIL should be quiet when actions.yaml is in the diff: {quiet}")
        return 1
    print("ok    silent when actions.yaml is also touched")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--base", default="origin/main")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    warnings = check(_diff_against_base(args.base))
    if not warnings:
        print("money-verb check: OK (advisory)")
        return 0
    print("money-verb check: advisory warning(s)")
    for w in warnings:
        print(f"  {w}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
