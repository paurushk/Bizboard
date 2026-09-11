"""Freeze Gate contract tests for the §G7 / §H4 / §H5 / §H9 GAPs in
docs/FREEZE_SCOPE_COVERAGE.md:

- audit-log append-only (no write path on AuditEvent / StatutoryDocumentEvent)
- security headers present on API responses
- HelpCode registry completeness (no orphan codes)
- boot-time config validation fails fast on a missing/weak secret
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys

import pytest

pytestmark = pytest.mark.django_db


# --- §H4: audit-log immutability -------------------------------------------------

_APPEND_ONLY_VIEWSETS = (
    ("core.views", "AuditEventViewSet"),
    ("core.views", "StatutoryDocumentEventViewSet"),
)


@pytest.mark.parametrize("module_path,name", _APPEND_ONLY_VIEWSETS)
def test_audit_viewsets_expose_no_write_path(module_path, name):
    from importlib import import_module

    from rest_framework import mixins

    vs = getattr(import_module(module_path), name)
    for forbidden in (
        mixins.CreateModelMixin,
        mixins.UpdateModelMixin,
        mixins.DestroyModelMixin,
    ):
        assert not issubclass(vs, forbidden), f"{name} must not be writable ({forbidden.__name__})"
    # and the resolved handler map has no unsafe verb
    handlers = getattr(vs, "http_method_names", [])
    for verb in ("post", "put", "patch", "delete"):
        # ViewSet.as_view() maps verbs to actions; a list-only viewset defines none
        assert not hasattr(vs, verb) or verb in ("options", "head", "get"), verb


def test_audit_event_write_endpoints_are_405(tenant_a):
    for url in ("/api/v1/audit/", "/api/v1/statutory-events/"):
        # list GET is allowed for the right role; writes must be method-not-allowed
        assert tenant_a.client.post(url, {}, format="json").status_code in (403, 405)
        assert tenant_a.client.delete(f"{url}1/").status_code in (403, 404, 405)
        assert tenant_a.client.patch(f"{url}1/", {}, format="json").status_code in (403, 404, 405)


# --- §H9: security headers -----------------------------------------------------

def test_api_response_carries_hardening_headers(tenant_a):
    resp = tenant_a.client.get("/api/v1/dashboard/")
    assert resp.status_code == 200
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("Referrer-Policy") == "same-origin"
    # clickjacking protection (XFrameOptionsMiddleware) — DENY or SAMEORIGIN
    assert resp.headers.get("X-Frame-Options", "").upper() in ("DENY", "SAMEORIGIN")
    # QOS-0011: a Content-Security-Policy is emitted; the API surface is locked down.
    csp = resp.headers.get("Content-Security-Policy", "")
    assert "default-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp


def test_admin_response_gets_a_form_and_static_compatible_csp(client, settings):
    """D-ops: the API-only DEFAULT policy's `form-action 'none'` / `default-src
    'none'` blocks Django admin's own login form and static CSS/JS outright —
    caught by actually logging into /admin/ live, not just reading the code.
    /admin/ must get a distinct policy that still allows same-origin form
    posts and same-origin static assets, while staying just as locked down
    against anything cross-origin or inline."""
    settings.ADMIN_ENABLED = True
    resp = client.get("/admin/login/")
    assert resp.status_code == 200
    csp = resp.headers.get("Content-Security-Policy", "")
    assert "form-action 'self'" in csp
    assert "script-src 'self'" in csp
    assert "style-src 'self'" in csp
    assert "form-action 'none'" not in csp
    assert "default-src 'none'" not in csp
    # still locked down against anything cross-origin / inline / framed.
    assert "frame-ancestors 'none'" in csp


def test_no_server_version_leak(tenant_a):
    resp = tenant_a.client.get("/api/v1/dashboard/")
    server = (resp.headers.get("Server") or "").lower()
    assert "django" not in server and "wsgi" not in server


# --- §H5: HelpCode registry completeness --------------------------------------

def test_every_helpcode_constant_is_registered():
    """Adding a `HelpCode.FOO` constant but forgetting `ALL_HELP_CODES` /
    `ERROR_CODE_TO_INTENT` would ship a code the FE help map can't resolve."""
    from core.help_codes import ALL_HELP_CODES, ERROR_CODE_TO_INTENT, HelpCode

    constants = {
        v for k, v in vars(HelpCode).items()
        if not k.startswith("_") and isinstance(v, str)
    }
    missing_from_all = constants - set(ALL_HELP_CODES)
    assert not missing_from_all, f"HelpCode constants absent from ALL_HELP_CODES: {missing_from_all}"

    missing_intent = set(ALL_HELP_CODES) - set(ERROR_CODE_TO_INTENT)
    assert not missing_intent, f"help codes with no FE intent mapping: {missing_intent}"


# --- §H5: boot-time config validation ----------------------------------------

def test_fail_fast_secrets_rejects_weak_secret_key():
    """`DJANGO_FAIL_FAST_SECRETS=1` with DEBUG off and a short SECRET_KEY must
    abort startup with ImproperlyConfigured, not boot silently."""
    import os

    env = dict(os.environ)
    env.pop("PYTEST_INMEMORY_DB", None)
    env.update(
        DJANGO_SETTINGS_MODULE="config.settings",
        DJANGO_FAIL_FAST_SECRETS="1",
        DJANGO_DEBUG="0",
        DJANGO_ENV="development",
        DJANGO_SECRET_KEY="too-short",
    )
    proc = subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        env=env, capture_output=True, text=True, timeout=90,
    )
    combined = proc.stderr + proc.stdout
    assert proc.returncode != 0, combined
    assert "ImproperlyConfigured" in combined, combined
    assert "DJANGO_SECRET_KEY" in combined, combined


def _settings_boot(**env_overrides):
    import os

    env = dict(os.environ)
    env.pop("PYTEST_INMEMORY_DB", None)
    env.update(DJANGO_SETTINGS_MODULE="config.settings", **env_overrides)
    return subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        env=env, capture_output=True, text=True, timeout=90,
    )


_PROD_BASE = dict(
    DJANGO_ENV="production", DJANGO_DEBUG="0", DJANGO_SECRET_KEY="x" * 50,
    ALLOWED_HOSTS="app.example.com",
    DATABASE_URL="postgresql://u:p@db.internal:5432/bizboard",
)


def test_production_requires_email_host():
    proc = _settings_boot(
        **_PROD_BASE, EMAIL_HOST="", CORS_ALLOWED_ORIGINS="https://app.example.com",
    )
    combined = proc.stderr + proc.stdout
    assert proc.returncode != 0, combined
    assert "EMAIL_HOST" in combined and "ImproperlyConfigured" in combined, combined


def test_production_rejects_localhost_only_cors():
    proc = _settings_boot(
        **_PROD_BASE, EMAIL_HOST="smtp.example.com",
        CORS_ALLOWED_ORIGINS="http://localhost:5173",
    )
    combined = proc.stderr + proc.stdout
    assert proc.returncode != 0, combined
    assert "CORS" in combined and "localhost" in combined, combined


# --- §H4 / §G7: FileAsset download — tenant scoping + filename sanitisation ---

def _upload_attachment(tenant, name="ok.pdf"):
    from core.models import FileAsset
    from django.core.files.base import ContentFile

    asset = FileAsset.objects.create(
        company=tenant.company, kind=FileAsset.Kind.ATTACHMENT, original_name=name,
        content_type="application/pdf", size=5,
    )
    asset.file.save(f"{asset.pk}.pdf", ContentFile(b"%PDF-1"), save=True)
    return asset


def test_file_download_is_tenant_scoped(tenant_a, tenant_b):
    asset = _upload_attachment(tenant_a)
    assert tenant_a.client.get(f"/api/v1/files/{asset.pk}/download/").status_code == 200
    # tenant B: the asset is not in its queryset -> 404, never another tenant's file
    assert tenant_b.client.get(f"/api/v1/files/{asset.pk}/download/").status_code == 404


def test_file_download_filename_is_sanitised(tenant_a):
    asset = _upload_attachment(tenant_a, name='../../etc/passwd"\r\nX-Injected: 1')
    resp = tenant_a.client.get(f"/api/v1/files/{asset.pk}/download/")
    assert resp.status_code == 200
    disp = resp.headers.get("Content-Disposition", "")
    assert "\r" not in disp and "\n" not in disp
    assert '"../../etc/passwd' not in disp  # quote / CRLF stripped by the view


# --- §H4: request-log PII masking -------------------------------------------

def test_request_log_masks_ids_and_carries_no_body(tenant_a):
    logger = logging.getLogger("bizboard.request")
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Capture(level=logging.INFO)
    logger.addHandler(handler)
    prev_level = logger.level
    logger.setLevel(logging.INFO)
    try:
        tenant_a.client.get(
            "/api/v1/sales/invoices/?search=9812345678&customer_phone=9812345678"
        )
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev_level)

    lines = [r.getMessage() for r in records]
    assert lines, "no request log emitted"
    entry = json.loads(lines[-1])
    # the query string (with a phone number) is never in the logged path
    assert "9812345678" not in entry["path"]
    assert "?" not in entry["path"]
    # ids are hashed, not raw
    assert entry["user_id"] and entry["user_id"] != str(tenant_a.owner.pk)
    assert len(entry["user_id"]) == 12
    # the log record has no body / headers / query keys
    assert set(entry) <= {
        "event", "request_id", "method", "path", "status", "duration_ms",
        "user_id", "company_id",
    }


# --- §G7: every CRUD mutation writes an AuditEvent -------------------------

def test_company_scoped_viewset_audits_every_crud_verb():
    """`CompanyScopedViewSet` is the base for all tenant CRUD — its
    perform_create / perform_update / perform_destroy each call the audit hook,
    so no mutation route can silently skip the activity log."""
    import inspect

    from core.viewsets import CompanyScopedViewSet

    for verb in ("perform_create", "perform_update", "perform_destroy"):
        src = inspect.getsource(getattr(CompanyScopedViewSet, verb))
        assert "_audit" in src, f"{verb} does not write an AuditEvent"


def test_crud_mutations_write_audit_events(tenant_a):
    from core.models import AuditEvent

    def _count(action, entity_id):
        return AuditEvent.objects.filter(
            company=tenant_a.company, entity_type="Customer",
            entity_id=str(entity_id), action=action,
        ).count()

    created = tenant_a.client.post(
        "/api/v1/customers/", {"name": "Audited Co", "state": "Karnataka"}, format="json"
    )
    assert created.status_code == 201, created.data
    cid = created.data["id"]
    assert _count("CREATE", cid) == 1

    upd = tenant_a.client.patch(f"/api/v1/customers/{cid}/", {"name": "Audited Co 2"}, format="json")
    assert upd.status_code == 200, upd.data
    assert _count("UPDATE", cid) == 1

    dele = tenant_a.client.delete(f"/api/v1/customers/{cid}/")
    assert dele.status_code in (204, 200), dele.status_code
    assert _count("DELETE", cid) == 1
