"""WP-CM2 — every SMS goes through a registered template (``SmsProvider.send_template``).

Indian operators drop SMS whose text does not match a DLT-registered template. A body built in a
caller and sent raw would look fine in tests and never arrive in production. Flags, outside
``core/services/sms.py``, any call to a raw sender (``send_text``, ``_send_text``, ``_send_otp``,
``_send_msg91``, ``_send_twilio``... — those also skip the WP-AB1 SMS caps), any import of a private
name from ``core.services.sms``, and any ``send_template("<key>")`` whose key is not in
``core/message_templates.py``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

NAME = "message_templates"
CONSEQUENCE = "An SMS sent with a raw body has no DLT template and is dropped by Indian operators."
# Every sender in core/services/sms.py that is not send_template (they skip the template and the caps).
_RAW = {"send_text", "_send_text", "_send_twilio_text", "_send_msg91_flow", "_send_otp", "_send_msg91", "_send_twilio"}


def _is_raw(name: str) -> bool:
    return name in _RAW
_SMS_MODULE = "backend/core/services/sms.py"


def _registered_keys(root: Path) -> set[str]:
    src = (root / "backend" / "core" / "message_templates.py")
    if not src.exists():
        return set()
    return set(re.findall(r'key="([a-z0-9_]+)"', src.read_text(encoding="utf-8")))


def check(root: Path) -> list[str]:
    violations: list[str] = []
    backend = root / "backend"
    if not backend.exists():
        return violations
    keys = _registered_keys(root)
    for path in sorted(backend.rglob("*.py")):
        if {".venv", "tests", "migrations", "node_modules"} & set(path.parts):
            continue
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        if "send_" not in text and "core.services.sms" not in text:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and rel != _SMS_MODULE and (node.module or "").endswith("services.sms"):
                for alias in node.names:
                    if alias.name.startswith("_"):
                        violations.append(f"{rel}:{node.lineno}: imports private SMS sender '{alias.name}'")
                continue
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else fn.id if isinstance(fn, ast.Name) else ""
            if _is_raw(name) and rel != _SMS_MODULE:
                violations.append(f"{rel}:{node.lineno}: raw SMS send '{name}'; use SmsProvider.send_template")
            if name == "send_template" and len(node.args) >= 2:
                arg = node.args[1]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value not in keys:
                    violations.append(f"{rel}:{node.lineno}: SMS template '{arg.value}' is not registered")
    return violations


def make_bad_tree(tmp: Path) -> None:
    d = tmp / "backend" / "payments"
    d.mkdir(parents=True, exist_ok=True)
    (d / "dunning.py").write_text(
        "from core.services.sms import _send_msg91 as quick\n"
        "def remind(phone):\n"
        "    SmsProvider.send_text(phone, 'Please pay now')\n"
        "    SmsProvider._send_otp(phone, '123456')\n"
        "    SmsProvider.send_template(phone, 'not_registered')\n",
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
