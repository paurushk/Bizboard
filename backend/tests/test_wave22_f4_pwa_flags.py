"""Wave 22 Sprint F4: PWA navigateFallback + no /api NetworkFirst cache (BB-000737/738/758)."""

from pathlib import Path

import pytest
from django.test import override_settings

REPO = Path(__file__).resolve().parents[2]


def test_bb_000737_758_navigate_fallback_is_offline_html():
    vite = (REPO / "web" / "vite.config.ts").read_text(encoding="utf-8")
    # Offline document is handlerDidError, not a NavigationRoute fallback.
    assert "navigateFallback: null" in vite
    assert "navigateFallback: '/offline.html'" not in vite
    assert 'navigateFallback: "/offline.html"' not in vite
    assert "navigateFallback: '/index.html'" not in vite
    assert 'navigateFallback: "/index.html"' not in vite
    assert "handlerDidError" in vite
    assert "offline.html" in vite
    assert "networkTimeoutSeconds: 10" in vite
    offline = (REPO / "web" / "public" / "offline.html").read_text(encoding="utf-8")
    assert "unregisterAndReload" in offline
    assert 'id="offline-title"' in offline


def test_bb_000738_api_not_network_first_cached():
    vite = (REPO / "web" / "vite.config.ts").read_text(encoding="utf-8")
    # /api must not be NetworkFirst-cached (status 0 poison / tenant residual).
    assert "bizboard-api" not in vite or "NetworkOnly" in vite
    # Dropped rule: no pathname.startsWith('/api') NetworkFirst block.
    if "pathname.startsWith('/api')" in vite or 'pathname.startsWith("/api")' in vite:
        # If a rule remains, it must be NetworkOnly without cacheable status 0.
        assert "NetworkOnly" in vite
        assert "cacheableResponse: { statuses: [0, 200] }" not in vite
        assert "statuses: [0, 200]" not in vite
    else:
        assert "NetworkFirst" in vite  # pages shell only
        assert "startsWith('/api')" not in vite
        assert 'startsWith("/api")' not in vite


@pytest.mark.django_db
@override_settings(DJANGO_ENV="production", GSP_CERTIFIED=False)
def test_bb_000742_gst_filing_sandbox_404_without_certified(tenant_a):
    resp = tenant_a.client.post(
        "/api/v1/reports/gst-filing-sandbox/",
        {"action": "upload_gstr1", "period": "2026-04"},
        format="json",
    )
    assert resp.status_code == 404
