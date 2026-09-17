"""4.6 — no support-impersonation / act-as-user API in the product.

Pilot isolation is company_id + JWT of the real user. An impersonation route
would bypass RBAC and tenant checks with a shared support cookie. Absence is
the control; this guard fails if one is introduced.
"""

from __future__ import annotations

import re
from pathlib import Path

NAME = "no_impersonation"
CONSEQUENCE = (
    "A support impersonation / act-as-user route would let staff become another "
    "tenant user and bypass Owner RBAC and company_id isolation."
)

_FORBIDDEN = re.compile(
    r"(impersonat|act_as_user|sudo_as|login_as_user|become_user|masquerade)",
    re.I,
)
# Bindings that actually expose a route or view, not a comment that says "do not impersonate".
_BINDING = re.compile(
    r"""(?:def|class|path\s*\(|re_path\s*\(|name\s*=)\s*['\"]?[^'\"\n]{0,80}"""
    r"""(?:impersonat|act_as_user|sudo_as|login_as_user|become_user|masquerade)""",
    re.I,
)
_SKIP_PARTS = {".venv", "migrations", "tests", "__pycache__", "node_modules"}


def check(root: Path) -> list[str]:
    violations: list[str] = []
    backend = root / "backend"
    if not backend.exists():
        return [f"{NAME}: backend/ not found under {root}"]
    for py in backend.rglob("*.py"):
        if set(py.parts) & _SKIP_PARTS:
            continue
        rel = py.relative_to(root).as_posix()
        try:
            content = py.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in _BINDING.finditer(content):
            line = content[: m.start()].count("\n") + 1
            violations.append(f"{rel}:{line}: {m.group(0).strip()[:80]}")
        # Catch a URL name that slipped past the binding regex.
        for i, raw in enumerate(content.splitlines(), 1):
            if "name=" in raw and _FORBIDDEN.search(raw) and not raw.lstrip().startswith("#"):
                snippet = raw.strip()[:80]
                marker = f"{rel}:{i}: {snippet}"
                if marker not in violations:
                    violations.append(marker)
    return violations


def make_bad_tree(tmp: Path) -> None:
    d = tmp / "backend" / "accounts"
    d.mkdir(parents=True, exist_ok=True)
    (d / "urls.py").write_text(
        "from django.urls import path\n"
        "from . import views\n"
        "urlpatterns = [path('impersonate/', views.impersonate, name='impersonate')]\n",
        encoding="utf-8",
    )
    (d / "views.py").write_text(
        "def impersonate(request):\n    return None\n",
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
