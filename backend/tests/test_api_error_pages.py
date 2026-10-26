"""WP-1 (ZAP 100001): unknown /api/ paths answer JSON; other paths keep Django's pages."""

import pytest
from django.test import override_settings

pytestmark = pytest.mark.django_db


@override_settings(DEBUG=False)
def test_unknown_api_path_is_a_json_404(client):
    res = client.get("/api/v1/sales/4986896388891880892")
    assert res.status_code == 404
    assert res["Content-Type"].startswith("application/json")
    assert res.json()["error"]["code"] == "not_found"


@override_settings(DEBUG=False)
def test_non_api_path_keeps_the_html_404(client):
    res = client.get("/definitely-not-a-page/")
    assert res.status_code == 404
    assert not res["Content-Type"].startswith("application/json")


def test_api_500_is_json_and_says_nothing_internal(rf):
    from core.error_pages import server_error

    res = server_error(rf.get("/api/v1/anything/"))
    assert res.status_code == 500 and b"server_error" in res.content and b"Traceback" not in res.content


def test_api_responses_may_not_be_embedded_by_other_sites(client):
    """WP-1 (ZAP 90004): Cross-Origin-Resource-Policy on API responses, not on public links."""
    res = client.get("/api/v1/health/")
    assert res["Cross-Origin-Resource-Policy"] == "same-site"
    public = client.get("/api/v1/public/pay/not-a-token/")
    assert "Cross-Origin-Resource-Policy" not in public


@override_settings(POSTGRES_RLS_ENABLED=True)
def test_health_probe_answers_even_when_binding_rls_would_fail(client, monkeypatch):
    """WP-6 game day: with Postgres down, set_rls_company raises; the probe must still answer itself
    (503 from its own DB check, 200 here where the DB is up) instead of the middleware's 500."""
    from django.db import OperationalError

    def boom(*_a, **_k):
        raise OperationalError("database is down")

    monkeypatch.setattr("core.rls.set_rls_company", boom)
    assert client.get("/api/v1/health/").status_code == 200
