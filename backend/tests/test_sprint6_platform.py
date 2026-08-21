"""Sprint 6 platform hygiene: FY close hidden, PWA unclaim, GSP PATCH, beat/logs."""

from pathlib import Path

import pytest
from django.test import RequestFactory, override_settings
from django.urls import get_resolver

from core.middleware import RequestIdMiddleware, _redact_path

pytestmark = pytest.mark.django_db

REPO = Path(__file__).resolve().parents[2]


def test_bb_000664_fy_close_is_routed():
    patterns = []

    def _walk(urlpatterns, prefix=""):
        for p in urlpatterns:
            route = prefix + str(getattr(p, "pattern", ""))
            if hasattr(p, "url_patterns"):
                _walk(p.url_patterns, route)
            else:
                patterns.append(route)

    _walk(get_resolver().url_patterns)
    joined = "\n".join(patterns).lower()
    assert "fy-close" in joined


def test_bb_000573_company_patch_cannot_write_gsp_credentials(tenant_a):
    resp = tenant_a.client.patch(
        "/api/v1/company/",
        {"gsp_credentials": {"client_id": "leak", "client_secret": "s3cret"}},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    tenant_a.company.refresh_from_db()
    assert not (tenant_a.company.gsp_credentials_encrypted or "")
    body = str(resp.data)
    assert "s3cret" not in body
    assert "gsp_credentials" not in (resp.data if isinstance(resp.data, dict) else {})


def test_bb_000580_pwa_has_offline_fallback():
    offline = REPO / "web" / "public" / "offline.html"
    assert offline.is_file()
    text = offline.read_text(encoding="utf-8").lower()
    assert "offline" in text
    # BB-000758: also assert vite navigateFallback (detailed in test_wave22_f4_pwa_flags).
    vite = (REPO / "web" / "vite.config.ts").read_text(encoding="utf-8")
    assert "offline.html" in vite
    assert "navigateFallback: '/offline.html'" in vite or 'navigateFallback: "/offline.html"' in vite


def test_bb_000575_capacitor_unclaimed_in_readme():
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "Not a store app" in readme
    mobile = (REPO / "mobile" / "README.md").read_text(encoding="utf-8").lower()
    assert "not" in mobile
    assert "play" in mobile and ("internal testing" in mobile or "play store" in mobile)
    assert "app store" in mobile
    assert (REPO / "mobile" / "android").is_dir()


def test_bb_000630_phasepages_split_started():
    phase = REPO / "web" / "src" / "pages" / "phase" / "PhasePages.tsx"
    reports = REPO / "web" / "src" / "pages" / "phase" / "AccountingReportsPages.tsx"
    banking = REPO / "web" / "src" / "pages" / "phase" / "BankingPhasePages.tsx"
    inventory = REPO / "web" / "src" / "pages" / "phase" / "InventoryPhasePages.tsx"
    assert phase.is_file()
    assert reports.is_file()
    assert banking.is_file()
    assert inventory.is_file()
    lines = phase.read_text(encoding="utf-8").count("\n") + 1
    assert lines < 80, f"PhasePages.tsx still a godfile ({lines} lines)"
    text = reports.read_text(encoding="utf-8")
    assert "export function ChartOfAccountsPage" in text
    assert "export const TrialBalancePage" in text


def test_bb_000594_jwt_access_lifetime_from_env():
    from django.conf import settings

    assert settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds() == 15 * 60
    settings_src = (REPO / "backend" / "config" / "settings.py").read_text(encoding="utf-8")
    assert "BB-000594" in settings_src
    assert "JWT_ACCESS_MINUTES" in settings_src


def test_bb_000636_no_duplicate_health_snapshot_beat():
    from django.conf import settings

    keys = set(settings.CELERY_BEAT_SCHEDULE)
    assert "insights-health-snapshots" not in keys
    assert "insights-daily-summaries" in keys


def test_bb_000587_request_path_redacts_document_numbers():
    assert _redact_path("/api/v1/sales/invoices/INV-2026-0001/") == "/api/v1/sales/invoices/:doc/"
    assert _redact_path("/api/v1/sales/invoices/") == "/api/v1/sales/invoices/"
    assert ":id" in _redact_path("/api/v1/files/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/")

    captured = {}

    class _Log:
        def info(self, msg):
            captured["msg"] = msg

    factory = RequestFactory()
    request = factory.get("/api/v1/sales/invoices/SI-99/")
    request.user = type("U", (), {"is_authenticated": False})()

    def _get_response(_req):
        from django.http import HttpResponse

        return HttpResponse("ok")

    mw = RequestIdMiddleware(_get_response)
    import core.middleware as mwmod

    original = mwmod.logger
    mwmod.logger = _Log()
    try:
        with override_settings(JSON_REQUEST_LOGS=True):
            mw(request)
    finally:
        mwmod.logger = original
    assert "SI-99" not in captured.get("msg", "")
    assert ":doc" in captured.get("msg", "")


def test_bb_000585_prod_compose_api_does_not_migrate_on_start():
    prod = (REPO / "docker-compose.prod.yml").read_text(encoding="utf-8")
    assert "must NOT migrate on start" in prod or "BB-000124" in prod
    # The api service command in prod overlay should not chain migrate && gunicorn.
    assert "migrate &&" not in prod.split("api:")[1].split("worker:")[0]


def test_bb_000595_erp_admin_modules_importable():
    from crm.admin import LeadAdmin, OpportunityAdmin
    from manufacturing.admin import BomAdmin, WorkOrderAdmin
    from payroll.admin import EmployeeAdmin, PayRunAdmin, PaySlipAdmin

    assert BomAdmin and WorkOrderAdmin
    assert EmployeeAdmin and PayRunAdmin and PaySlipAdmin
    assert LeadAdmin and OpportunityAdmin


def test_bb_000598_adrs_adopted():
    adrs = (REPO / "docs" / "reviews" / "ARCHITECTURAL_DECISIONS.md").read_text(encoding="utf-8")
    assert "ADR-A19" in adrs and "Accepted" in adrs
    assert "ADR-A20" in adrs
    assert "ADR-A21" in adrs


def test_bb_000591_competitor_honesty():
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    competitor = (REPO / "docs" / "reviews" / "18_COMPETITOR_ANALYSIS.md").read_text(encoding="utf-8")
    assert "BB-000591" in readme or "Not Zoho" in readme
    assert "BB-000591" in competitor
