"""WP-M1 — every backend app that owns tenant data has a row in docs/ops/MODULE_READINESS.md.

A new module that stores company data must say how it meets the SaaS rules (row-level security,
ledger postings, invariants, background jobs, runbook) before it ships. Static check: an app
directory whose models.py declares a ``company = models.ForeignKey(...)`` / ``OneToOneField`` (or
inherits ``CompanyScopedModel``) must appear as `` `app` `` in the table.
"""

from __future__ import annotations

import re
from pathlib import Path

NAME = "module_readiness"
CONSEQUENCE = (
    "A module that stores tenant data shipped without saying how it handles row-level security, "
    "ledger postings, invariants, background jobs and its runbook."
)

_TENANT = re.compile(r"(\bcompany\s*=\s*models\.(ForeignKey|OneToOneField)\(|\(CompanyScopedModel\b|\(DocumentTotalsModel\b)")
_ROW = re.compile(r"^\|\s*`([a-z_]+)`\s*\|", re.M)


def _tenant_apps(backend: Path) -> set[str]:
    apps = set()
    for models_py in backend.glob("*/models.py"):
        text = models_py.read_text(encoding="utf-8", errors="ignore")
        if _TENANT.search(text):
            apps.add(models_py.parent.name)
    for pkg in backend.glob("*/models/__init__.py"):
        text = "".join(p.read_text(encoding="utf-8", errors="ignore") for p in pkg.parent.glob("*.py"))
        if _TENANT.search(text):
            apps.add(pkg.parent.parent.name)
    return apps


def check(root: Path) -> list[str]:
    backend = root / "backend"
    doc = root / "docs" / "ops" / "MODULE_READINESS.md"
    if not backend.exists():
        return [f"{NAME}: backend/ not found under {root}"]
    listed = set(_ROW.findall(doc.read_text(encoding="utf-8"))) if doc.exists() else set()
    missing = sorted(_tenant_apps(backend) - listed)
    return [f"{app}: stores tenant data but has no row in docs/ops/MODULE_READINESS.md" for app in missing]


def make_bad_tree(tmp: Path) -> None:
    app = tmp / "backend" / "newmodule"
    app.mkdir(parents=True, exist_ok=True)
    (app / "models.py").write_text(
        "from django.db import models\n"
        "class Thing(models.Model):\n"
        "    company = models.ForeignKey('accounts.Company', on_delete=models.CASCADE)\n",
        encoding="utf-8",
    )
    (tmp / "docs" / "ops").mkdir(parents=True, exist_ok=True)
    (tmp / "docs" / "ops" / "MODULE_READINESS.md").write_text("| App |\n|---|\n", encoding="utf-8")


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
