"""4.6 — no impersonation / act-as-user API."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from django.urls import URLPattern, URLResolver, get_resolver

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[2]

_guard_file = ROOT / "scripts" / "ci_gates" / "guards" / "guard_no_impersonation.py"
if _guard_file.is_file():
    _guard_spec = importlib.util.spec_from_file_location(
        "guard_no_impersonation", _guard_file
    )
    _guard = importlib.util.module_from_spec(_guard_spec)
    _guard_spec.loader.exec_module(_guard)
    _FORBIDDEN = _guard._FORBIDDEN
else:
    _FORBIDDEN = None


def _walk(patterns, prefix=""):
    found: list[str] = []
    for p in patterns:
        if isinstance(p, URLResolver):
            found.extend(_walk(p.url_patterns, prefix + str(p.pattern)))
            continue
        if not isinstance(p, URLPattern):
            continue
        name = p.name or ""
        route = prefix + str(p.pattern)
        callback = getattr(p, "callback", None)
        cb_name = getattr(callback, "__name__", "") or ""
        cls = getattr(callback, "view_class", None)
        cls_name = cls.__name__ if cls is not None else ""
        blob = f"{name} {route} {cb_name} {cls_name}"
        if _FORBIDDEN.search(blob):
            found.append(blob.strip())
    return found


def test_urlconf_has_no_impersonation_routes():
    if _FORBIDDEN is None:
        pytest.skip("scripts/ci_gates not present outside repo checkout")
    hits = _walk(get_resolver().url_patterns)
    assert hits == [], hits


@pytest.mark.parametrize(
    "path",
    (
        "/api/v1/auth/impersonate/",
        "/api/v1/auth/act-as/",
        "/api/v1/auth/sudo/",
        "/api/v1/support/impersonate/",
        "/admin/impersonate/",
    ),
)
def test_impersonation_paths_are_404(tenant_a, path):
    resp = tenant_a.client.post(path, {}, format="json")
    assert resp.status_code in (404, 301, 302), (path, resp.status_code, resp.data)


def test_web_src_has_no_impersonation_routes():
    src = ROOT / "web" / "src"
    if _FORBIDDEN is None or not src.is_dir():
        pytest.skip("web/src not present outside repo checkout")
    hits: list[str] = []
    for path in src.rglob("*"):
        if path.suffix not in {".ts", ".tsx", ".js", ".jsx"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if _FORBIDDEN.search(text):
            hits.append(path.relative_to(ROOT).as_posix())
    assert hits == [], hits
