"""WP-CM1 — email goes through ``core.mail.send`` so bounced and complained addresses are skipped.

Sending with ``django.core.mail.send_mail`` / ``EmailMessage`` directly bypasses the suppression
list and the unsubscribe headers; repeated sends to bad addresses hurt the sender reputation that
OTP and invoice emails depend on. Outside ``backend/core/mail.py`` this flags (by syntax tree, so
aliases are caught) any import from ``django.core.mail``, and any call to ``send_mail`` /
``send_mass_mail`` / ``EmailMessage`` / ``EmailMultiAlternatives`` / ``mail_admins`` /
``mail_managers`` / ``.email_user(`` (Django's ``User.email_user`` calls ``send_mail``).
"""

from __future__ import annotations

import ast
from pathlib import Path

NAME = "no_direct_send_mail"
CONSEQUENCE = "Email sent around core.mail ignores bounces and complaints and erodes deliverability."
_CALLS = {"send_mail", "send_mass_mail", "EmailMessage", "EmailMultiAlternatives", "mail_admins",
          "mail_managers", "email_user"}
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
        text = path.read_text(encoding="utf-8", errors="replace")
        if "mail" not in text:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("django.core.mail"):
                out.append(f"{rel}:{node.lineno}: imports from django.core.mail; send with core.mail.send")
            elif isinstance(node, ast.Import) and any(a.name.startswith("django.core.mail") for a in node.names):
                out.append(f"{rel}:{node.lineno}: imports django.core.mail; send with core.mail.send")
            elif isinstance(node, ast.Call):
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) else fn.id if isinstance(fn, ast.Name) else ""
                if name in _CALLS:
                    out.append(f"{rel}:{node.lineno}: send email with core.mail.send, not {name}")
    return out


def make_bad_tree(tmp: Path) -> None:
    d = tmp / "backend" / "billing"
    d.mkdir(parents=True, exist_ok=True)
    (d / "dunning.py").write_text(
        "from django.core.mail import send_mail as sm\n"
        "def remind(user):\n"
        "    sm('s', 'b', 'f', ['x@y.in'])\n"
        "    user.email_user('s', 'b')\n",
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
