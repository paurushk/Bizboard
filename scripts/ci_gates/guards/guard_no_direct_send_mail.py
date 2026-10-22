"""WP-CM1 — email goes through ``core.mail.send`` so bounced and complained addresses are skipped.

Sending with ``django.core.mail.send_mail`` / ``EmailMessage`` directly bypasses the suppression
list and the unsubscribe headers; repeated sends to bad addresses hurt the sender reputation that
OTP and invoice emails depend on. Flags any such call outside ``backend/core/mail.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

NAME = "no_direct_send_mail"
CONSEQUENCE = "Email sent around core.mail ignores bounces and complaints and erodes deliverability."
_CALL = re.compile(r"\b(send_mail|send_mass_mail|EmailMessage|EmailMultiAlternatives)\s*\(")
_ALLOWED = {"backend/core/mail.py"}


def check(root: Path) -> list[str]:
    out: list[str] = []
    backend = root / "backend"
    if not backend.exists():
        return out
    for path in sorted(backend.rglob("*.py")):
        if {".venv", "tests", "migrations", "node_modules"} & set(path.parts):
            continue
        rel = path.relative_to(root).as_posix()
        if rel in _ALLOWED:
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if _CALL.search(line):
                out.append(f"{rel}:{i}: send email with core.mail.send, not {_CALL.search(line).group(1)}")
    return out


def make_bad_tree(tmp: Path) -> None:
    d = tmp / "backend" / "billing"
    d.mkdir(parents=True, exist_ok=True)
    (d / "dunning.py").write_text("send_mail('s', 'b', 'f', ['x@y.in'])\n", encoding="utf-8")


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
