"""7.7 — new migrations must be expand-only unless EXPAND_CONTRACT_OK is documented.

A RemoveField / RenameField / DeleteModel in the same release as readers still
need the column causes zero-downtime deploys to 500. Mark the file with
EXPAND_CONTRACT_OK only after the expand deploy has shipped.
"""

from __future__ import annotations

import re
from pathlib import Path

NAME = "zdt_migrations"
CONSEQUENCE = (
    "A destructive Django migration without EXPAND_CONTRACT_OK ships a "
    "contract-phase drop before readers are gone; rolling deploys 500."
)

_DESTRUCTIVE = re.compile(
    r"\b(RemoveField|RenameField|DeleteModel|RenameModel)\b"
)
_OK = "EXPAND_CONTRACT_OK"


def check(root: Path) -> list[str]:
    backend = root / "backend"
    violations: list[str] = []
    if not backend.exists():
        return [f"{NAME}: backend/ not found under {root}"]
    for py in backend.rglob("migrations/*.py"):
        parts = set(py.parts)
        if ".venv" in parts or "__pycache__" in parts:
            continue
        if py.name == "__init__.py":
            continue
        try:
            content = py.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if _OK in content:
            continue
        if _DESTRUCTIVE.search(content):
            rel = py.relative_to(root).as_posix()
            violations.append(f"{rel}: destructive op without {_OK}")
    return violations


def make_bad_tree(tmp: Path) -> None:
    d = tmp / "backend" / "sales" / "migrations"
    d.mkdir(parents=True, exist_ok=True)
    (d / "0099_drop_column.py").write_text(
        "from django.db import migrations\n"
        "class Migration(migrations.Migration):\n"
        "    operations = [migrations.RemoveField(model_name='x', name='y')]\n",
        encoding="utf-8",
    )
