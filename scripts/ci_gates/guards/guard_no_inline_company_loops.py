"""WP-E2 — a Celery task must not do per-company work inside one loop over every company.

An inline loop does not finish at thousands of tenants, lets one company's failure stop
the rest, and (worst) runs with no tenant set, so under FORCE RLS it reads nothing.
Copy the orchestrator pattern instead: read company ids, then ``.delay(company_id=pk)``
one task per company (see ``core.tasks.nightly_invariants_task``).

Flags ``for ... in <...>Company.objects...`` (or a list built from it) in ``*/tasks.py``
whose loop body does anything other than queue a task. Allow a deliberate case with a
``# inline-company-loop-ok: <reason>`` comment on the ``for`` line.
"""

from __future__ import annotations

import ast
from pathlib import Path

NAME = "no_inline_company_loops"
CONSEQUENCE = (
    "A task that loops every company inline runs tenant-blind under RLS, stops at the first crash, "
    "and does not finish at SaaS scale."
)
_ALLOW = "inline-company-loop-ok:"
_QUEUE_CALLS = {"delay", "apply_async"}


def _mentions_company_queryset(node: ast.AST) -> bool:
    src = ast.unparse(node)
    return "Company.objects" in src or "company_ids" in src or "all_company_ids" in src


def _body_only_queues(body: list[ast.stmt]) -> bool:
    """Each statement queues a task (``x.delay(...)``), bumps a counter, or is pass/continue."""
    for stmt in body:
        if isinstance(stmt, (ast.Pass, ast.Continue, ast.AugAssign)):
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            fn = stmt.value.func
            if isinstance(fn, ast.Attribute) and fn.attr in _QUEUE_CALLS:
                continue
        return False
    return True


def check(root: Path) -> list[str]:
    violations: list[str] = []
    backend = root / "backend"
    for path in sorted(backend.rglob("tasks.py")) if backend.exists() else []:
        if {".venv", "tests", "migrations"} & set(path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            violations.append(f"{path.relative_to(root).as_posix()}: cannot parse ({exc})")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.For) or not _mentions_company_queryset(node.iter):
                continue
            if _ALLOW in lines[node.lineno - 1]:
                continue
            if not _body_only_queues(node.body):
                rel = path.relative_to(root).as_posix()
                violations.append(f"{rel}:{node.lineno}: loop over companies does work inline; fan out instead")
    return violations


def make_bad_tree(tmp: Path) -> None:
    d = tmp / "backend" / "billing"
    d.mkdir(parents=True, exist_ok=True)
    (d / "tasks.py").write_text(
        "def nightly():\n"
        "    for company in Company.objects.all():\n"
        "        do_heavy_work(company)\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    import sys

    root = Path(__file__).resolve().parents[3]
    out = check(root)
    if out:
        print(f"GUARD FAIL {NAME}:")
        for v in out:
            print(f"  - {v}")
        sys.exit(1)
    print(f"GUARD OK {NAME}")
