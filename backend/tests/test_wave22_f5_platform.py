"""Wave 22 Sprint F5 — platform / DevOps / observability gates."""

import inspect
from pathlib import Path

import pytest
from django.test import override_settings

ROOT = Path(__file__).resolve().parents[2]


def test_bb_000709_celery_doc_id_keys_include_note_id():
    from config.celery import _DOC_ID_KEYS

    assert "note_id" in _DOC_ID_KEYS
    assert "challan_id" in _DOC_ID_KEYS
    assert "notification_id" in _DOC_ID_KEYS


def test_bb_000714_compose_api_command_has_no_migrate():
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "python manage.py migrate &&" not in text
    assert 'profiles: ["migrate"]' in text
    assert "gunicorn config.wsgi:application" in text


def test_bb_000710_compose_rls_not_hard_pinned():
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert 'POSTGRES_RLS_ENABLED: "0"' not in text
    assert "${POSTGRES_RLS_ENABLED:-0}" in text


def test_bb_000746_android_allow_backup_false():
    manifest = ROOT / "mobile" / "android" / "app" / "src" / "main" / "AndroidManifest.xml"
    assert manifest.is_file()
    text = manifest.read_text(encoding="utf-8")
    assert 'android:allowBackup="false"' in text
    assert 'android:allowBackup="true"' not in text


def test_bb_000755_nginx_no_cache_for_index_and_sw():
    nginx = ROOT / "web" / "nginx.conf"
    assert nginx.is_file()
    text = nginx.read_text(encoding="utf-8")
    assert "location = /index.html" in text
    assert "no-cache" in text
    assert "sw.js" in text or "workbox" in text


def test_bb_000754_recon_list_does_not_save():
    """GET recon must be compute-only — no .save() of SUGGESTED (BB-000754)."""
    from payments.views import ReconViewSet

    list_src = inspect.getsource(ReconViewSet.list)
    assert ".save(" not in list_src
    assert "suggest_matches" in list_src
    suggest_src = inspect.getsource(ReconViewSet.suggest)
    assert ".save(" in suggest_src


def test_bb_000753_metrics_endpoint_registered():
    from django.urls import reverse

    assert reverse("metrics-root") == "/metrics/"
    assert reverse("v1:metrics") == "/api/v1/metrics/"


@pytest.mark.django_db
@override_settings(METRICS_TOKEN="test-metrics-token")
def test_bb_000753_metrics_returns_counter():
    from django.test import Client

    client = Client()
    assert client.get("/metrics/").status_code == 401
    resp = client.get("/metrics/", HTTP_AUTHORIZATION="Bearer test-metrics-token")
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    assert "bizboard_http_requests_total" in body
