"""1.1 — Table B dark flags stay off in freeze deploy artifacts.

A CD/compose default of VITE_ENABLE_GSTR=true ships GSTR screens in the frozen
pilot UI. Exceptions must be explicit (FREEZE_EXCEPTION token) and Human-signed.
"""

from __future__ import annotations

import re
from pathlib import Path

NAME = "freeze_table_b_defaults"
CONSEQUENCE = (
    "A freeze Table B module (GSTR screens, manufacturing, payroll, CRM, Tally, "
    "live e-invoice submit) defaults on in a deploy artifact and ships dark UI."
)

# Flag=on patterns that are forbidden in freeze deploy files unless the file
# also contains FREEZE_EXCEPTION.
_ON = re.compile(
    r"(?im)^(?:export\s+)?(?P<key>"
    r"ENABLE_GSTR|ENABLE_GSTN_JSON|ENABLE_TALLY|ENABLE_MANUFACTURING|"
    r"ENABLE_PAYROLL|ENABLE_CRM|ENABLE_FIXED_ASSETS|ENABLE_BOE|"
    r"ENABLE_WHATSAPP_CLOUD|ENABLE_ACCOUNT_AGGREGATOR|"
    r"VITE_ENABLE_GSTR|VITE_ENABLE_TALLY|VITE_ENABLE_EINVOICE_SUBMIT|"
    r"VITE_ENABLE_MANUFACTURING|VITE_ENABLE_PAYROLL|VITE_ENABLE_CRM|"
    r"VITE_ENABLE_AI|GSP_LIVE_ENABLED"
    r")\s*[=:]\s*(?:true|1|yes)\b"
)
_COMPOSE_ON = re.compile(
    r"(?im)(VITE_ENABLE_GSTR|VITE_ENABLE_EINVOICE_SUBMIT|VITE_ENABLE_TALLY|"
    r"VITE_ENABLE_MANUFACTURING|VITE_ENABLE_PAYROLL|VITE_ENABLE_CRM|"
    r"VITE_ENABLE_AI)\s*[:=].*?(?:true|1)"
)

_FILES = (
    ".env.production.example",
    ".env.staging.example",
    ".env.pilot.example",
    "backend/.env.pilot.example",
    "web/.env.pilot.example",
    "web/.env.example",
    ".github/workflows/cd.yml",
    "docker-compose.yml",
    "docker-compose.prod.yml",
    "docker-compose.staging.yml",
)


def check(root: Path) -> list[str]:
    violations: list[str] = []
    for rel in _FILES:
        path = root / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "FREEZE_EXCEPTION" in text:
            continue
        for rx in (_ON, _COMPOSE_ON):
            for m in rx.finditer(text):
                line = text[: m.start()].count("\n") + 1
                snippet = m.group(0).strip()[:80]
                violations.append(f"{rel}:{line}: {snippet}")
    return violations


def make_bad_tree(tmp: Path) -> None:
    (tmp / ".env.production.example").write_text("ENABLE_GSTR=1\n", encoding="utf-8")


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
