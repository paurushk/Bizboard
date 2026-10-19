"""RPT phase 1: GST export permission, GST audit trail accuracy, TDS/TCS worksheet access."""

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from accounts.models import CompanyUser, User
from core.models import AuditEvent

pytestmark = pytest.mark.django_db

PERIOD = "2026-07"


def _member(tenant, role, *, export=False, reports=True, tag="m"):
    user = User.objects.create_user(
        email=f"{tag}-{role.lower()}@{tenant.company.id}.test", password="StrongPass123!", full_name=tag,
    )
    CompanyUser.objects.create(
        company=tenant.company, user=user, role=role,
        can_view_financial_reports=reports, can_export=export,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _gstr_on(tenant):
    flags = dict(tenant.company.feature_flags or {})
    flags.update({"ENABLE_GSTR": True, "ENABLE_GSTN_JSON": True})
    tenant.company.feature_flags = flags
    tenant.company.save(update_fields=["feature_flags"])


def _audit_count(tenant):
    return AuditEvent.objects.filter(company=tenant.company, entity_type="GstReturnJson").count()


def test_gstr_preview_is_not_audited_as_a_download(tenant_a):
    _gstr_on(tenant_a)
    before = _audit_count(tenant_a)
    resp = tenant_a.client.get("/api/v1/reports/gstr1/", {"period": PERIOD})
    assert resp.status_code == 200
    assert _audit_count(tenant_a) == before


def test_gstr_xlsx_export_and_snapshot_are_audited(tenant_a):
    _gstr_on(tenant_a)
    before = _audit_count(tenant_a)
    assert tenant_a.client.get("/api/v1/reports/gstr1/", {"period": PERIOD, "format": "xlsx"}).status_code == 200
    assert _audit_count(tenant_a) == before + 1
    assert tenant_a.client.get("/api/v1/reports/gstr1/", {"period": PERIOD, "persist": "1"}).status_code == 200
    assert _audit_count(tenant_a) == before + 2


@override_settings(ENABLE_GSTN_JSON=True)
def test_gstn_json_needs_export_rights(tenant_a):
    _gstr_on(tenant_a)
    viewer = _member(tenant_a, "ACCOUNTANT", export=False)
    exporter = _member(tenant_a, "MANAGER", export=True, tag="exp")
    params = {"period": PERIOD, "format": "gstn-json"}
    assert viewer.get("/api/v1/reports/gstr1/", params).status_code == 403
    assert exporter.get("/api/v1/reports/gstr1/", params).status_code == 200
    # a plain preview stays open to anyone who may read financial reports
    assert viewer.get("/api/v1/reports/gstr1/", {"period": PERIOD}).status_code == 200


def _tds_on(tenant):
    flags = dict(tenant.company.feature_flags or {})
    flags["ENABLE_TDS"] = True
    tenant.company.feature_flags = flags
    tenant.company.save(update_fields=["feature_flags"])


@pytest.mark.parametrize("kind", ["tds", "tcs"])
def test_tax_worksheet_access_matrix(tenant_a, kind):
    _tds_on(tenant_a)
    url = f"/api/v1/reports/{kind}-worksheet/"
    accountant = _member(tenant_a, "ACCOUNTANT", export=False, tag="acc")
    accountant_x = _member(tenant_a, "ACCOUNTANT", export=True, tag="accx")
    manager = _member(tenant_a, "MANAGER", export=True, tag="mgr")

    # preview: owner and accountant yes, staff and manager no
    assert tenant_a.client.get(url, {"period": PERIOD, "preview": "1"}).status_code == 200
    assert accountant.get(url, {"period": PERIOD, "preview": "1"}).status_code == 200
    assert manager.get(url, {"period": PERIOD, "preview": "1"}).status_code == 403
    assert tenant_a.staff_client.get(url, {"period": PERIOD, "preview": "1"}).status_code == 403

    # CSV needs export rights as well
    assert accountant.get(url, {"period": PERIOD}).status_code == 403
    assert accountant_x.get(url, {"period": PERIOD}).status_code == 200
    assert tenant_a.client.get(url, {"period": PERIOD}).status_code == 200


def test_tax_worksheet_preview_shape(tenant_a):
    _tds_on(tenant_a)
    data = tenant_a.client.get(
        "/api/v1/reports/tds-worksheet/", {"period": PERIOD, "preview": "1"},
    ).json()
    payload = data.get("data", data)
    assert payload["kind"] == "tds"
    assert payload["count"] == 0
    assert "totals" in payload and "bySection" in payload


def test_tax_worksheet_off_company_gets_a_readable_error(tenant_a):
    with override_settings(ENABLE_TDS=False):
        resp = tenant_a.client.get("/api/v1/reports/tds-worksheet/", {"period": PERIOD, "preview": "1"})
    assert resp.status_code == 400
    assert "TDS/TCS" in resp.content.decode()


@pytest.mark.parametrize("path", ["/api/v1/reports/invoice-profit/", "/api/v1/reports/invoice-profit/rollup/"])
def test_margin_reports_are_for_owner_and_accountant_only(tenant_a, path):
    """RPT-12 / D4: cost and margin need the owner or an accountant, not just report access."""
    accountant = _member(tenant_a, "ACCOUNTANT", tag="acc")
    manager = _member(tenant_a, "MANAGER", tag="mgr")
    assert tenant_a.client.get(path).status_code == 200
    assert accountant.get(path).status_code == 200
    assert manager.get(path).status_code == 403
    assert tenant_a.staff_client.get(path).status_code == 403


def test_gst_snapshot_list_and_row_document_ids(tenant_a):
    """RPT-07: saved snapshots can be listed, and GSTR-1 gives the document ids behind its rows."""
    from tests.test_gst_returns import _setup_gst_month

    _gstr_on(tenant_a)
    _setup_gst_month(tenant_a)
    resp = tenant_a.client.get("/api/v1/reports/gstr1/", {"period": PERIOD, "persist": "1"})
    assert resp.status_code == 200
    ids = resp.data["document_ids"]
    b2b_numbers = {r["invoice_number"] for r in resp.data["b2b"]}
    assert b2b_numbers and b2b_numbers <= set(ids["sales_invoice"])
    assert all(isinstance(v, int) for v in ids["sales_invoice"].values())

    listed = tenant_a.client.get("/api/v1/reports/gst-snapshots/", {"return_type": "gstr1"})
    assert listed.status_code == 200
    body = listed.json()
    body = body.get("data", body)
    assert body["count"] == 1
    assert body["results"][0]["returnType"] == "GSTR1" and body["results"][0]["period"] == PERIOD

    # a staff user without report access cannot read them
    assert tenant_a.staff_client.get("/api/v1/reports/gst-snapshots/").status_code == 403
    # the GSTN-shaped file does not carry the screen-only ids
    from reporting.gst_returns import to_gstn_json

    assert "document_ids" not in to_gstn_json(dict(resp.data))
