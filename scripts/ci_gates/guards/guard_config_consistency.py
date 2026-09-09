"""FG-1: every feature flag in the code is classified in docs/FREEZE_SCOPE.md.

The freeze scope is only meaningful if it stays in sync with the code. This
guard extracts:

  * backend product flags  -- every ``_env_bool("X")`` in backend/config/settings.py
  * frontend feature flags -- every ``VITE_ENABLE_*`` / ``VITE_PILOT_ADVANCED``
    / ``VITE_HELP_V2`` referenced under web/src

and fails if any of them is not named somewhere in docs/FREEZE_SCOPE.md
(either in the section E table or in the operational-toggle allow-list
paragraph). A new flag added to the code without a scope decision is exactly
the drift this catches (see also the Python-version note in GATE_INVENTORY.md).
"""

from __future__ import annotations

import re
from pathlib import Path

NAME = "config_consistency"
CONSEQUENCE = (
    "A feature flag exists in the code but is not classified in FREEZE_SCOPE.md; "
    "the frozen surface is undefined for that flag and no test asserts its state."
)

_ENV_BOOL = re.compile(r'_env_bool\(\s*"([A-Z][A-Z0-9_]+)"')
_VITE = re.compile(r"\bVITE_(?:ENABLE_[A-Z0-9_]+|PILOT_ADVANCED|HELP_V2)\b")
_DOC_TOKEN = re.compile(r"`([A-Za-z][A-Za-z0-9_]+)`")


def _doc_tokens(root: Path) -> set[str]:
    doc = root / "docs" / "FREEZE_SCOPE.md"
    if not doc.exists():
        return set()
    return set(_DOC_TOKEN.findall(doc.read_text(encoding="utf-8")))


def _backend_flags(root: Path) -> set[str]:
    settings = root / "backend" / "config" / "settings.py"
    if not settings.exists():
        return set()
    return set(_ENV_BOOL.findall(settings.read_text(encoding="utf-8", errors="ignore")))


def _frontend_flags(root: Path) -> set[str]:
    web_src = root / "web" / "src"
    found: set[str] = set()
    if not web_src.exists():
        return found
    for f in list(web_src.rglob("*.ts")) + list(web_src.rglob("*.tsx")):
        try:
            found.update(_VITE.findall(f.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            continue
    return found


def check(root: Path) -> list[str]:
    doc = _doc_tokens(root)
    if not doc:
        return [f"{NAME}: docs/FREEZE_SCOPE.md not found or has no flag tokens"]
    problems: list[str] = []
    for flag in sorted(_backend_flags(root)):
        if flag not in doc:
            problems.append(
                f"{NAME}: backend flag _env_bool(\"{flag}\") is not classified in "
                f"docs/FREEZE_SCOPE.md (add it to section E or the operational allow-list)"
            )
    for flag in sorted(_frontend_flags(root)):
        if flag not in doc:
            problems.append(
                f"{NAME}: frontend flag {flag} is used in web/src but not classified "
                f"in docs/FREEZE_SCOPE.md"
            )
    return problems


def make_bad_tree(tmp: Path) -> None:
    (tmp / "docs").mkdir(parents=True, exist_ok=True)
    (tmp / "docs" / "FREEZE_SCOPE.md").write_text("classified: `ENABLE_KNOWN`\n", encoding="utf-8")
    (tmp / "backend" / "config").mkdir(parents=True, exist_ok=True)
    (tmp / "backend" / "config" / "settings.py").write_text(
        'X = _env_bool("ENABLE_KNOWN")\nY = _env_bool("ENABLE_UNCLASSIFIED_NEW_FLAG")\n',
        encoding="utf-8",
    )


if __name__ == "__main__":
    import sys

    root = Path(__file__).resolve().parents[3]
    out = check(root)
    if out:
        print(f"GUARD FAIL {NAME}:")
        for v in out:
            print("  ", v)
        sys.exit(1)
    print(f"GUARD OK {NAME}")
