"""PR 9 — R-015/035/036/037/038/040/041/044/048/052/054/056 P2 edges."""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.test import RequestFactory, override_settings
from django.utils import translation

from core.csv_utils import csv_safe
from core.exceptions import BusinessRuleError
from core.middleware import MaxBodySizeMiddleware
from core.models import AuditEvent
from core.services.billing import build_totals_preview
from core.services.feature_flags import build_feature_flags
from core.services.whatsapp import _whatsapp_language_code, send_whatsapp_template
from insights.models import BusinessHealthSnapshot, DailyBusinessSummary
from inventory.models import Warehouse
from inventory.services import InventoryService
from masters.pricing import assert_slab_bounds, assert_slab_payloads
from purchases.models import PurchaseInvoice
from reporting.gstr2b import match_gstr2b_to_purchases
from reporting.models import Gstr2bIngest
from tests.conftest import make_product, make_supplier

pytestmark = pytest.mark.django_db


def test_r040_csv_safe_prefixes_tab_cr_lf():
    assert csv_safe("\t=HYPERLINK") == "'\t=HYPERLINK"
    assert csv_safe("\r=CMD") == "'\r=CMD"
    assert csv_safe("\n@SUM") == "'\n@SUM"
    assert csv_safe("ok") == "ok"


@override_settings(MAX_REQUEST_BODY_SIZE=64)
def test_r035_undeclared_body_over_max_is_413():
    seen = {"called": False}

    def view(request):
        seen["called"] = True
        from django.http import HttpResponse

        return HttpResponse("ok")

    mw = MaxBodySizeMiddleware(view)
    rf = RequestFactory()
    req = rf.post("/api/v1/x/", data=b"x" * 200, content_type="application/octet-stream")
    req.META.pop("CONTENT_LENGTH", None)
    if hasattr(req, "_body"):
        delattr(req, "_body")
    req._read_started = False
    req._stream = io.BytesIO(b"x" * 200)
    resp = mw(req)
    assert resp.status_code == 413
    assert seen["called"] is False


@override_settings(MAX_REQUEST_BODY_SIZE=64)
def test_r035_declared_content_length_over_max_is_413():
    def view(request):
        from django.http import HttpResponse

        return HttpResponse("ok")

    mw = MaxBodySizeMiddleware(view)
    rf = RequestFactory()
    req = rf.post("/api/v1/x/", data=b"x" * 10, content_type="application/octet-stream")
    req.META["CONTENT_LENGTH"] = "99999"
    resp = mw(req)
    assert resp.status_code == 413


def test_r037_rejects_inverted_and_overlapping_slabs():
    with pytest.raises(BusinessRuleError):
        assert_slab_bounds(Decimal("10"), Decimal("5"))
    with pytest.raises(BusinessRuleError):
        assert_slab_payloads(
            [
                {"product": 1, "min_qty": "1", "max_qty": "20"},
                {"product": 1, "min_qty": "10", "max_qty": "30"},
            ]
        )


def test_r038_purchase_list_bad_date_is_400(tenant_a):
    resp = tenant_a.client.get("/api/v1/purchases/invoices/?date_from=foo")
    assert resp.status_code == 400, resp.data
    assert "date_from" in str(resp.data).lower()


def test_r036_product_list_fresh_after_patch(tenant_a):
    product = make_product(tenant_a.company, name="Cached Widget", sku="CW-1")
    listed = tenant_a.client.get("/api/v1/products/")
    assert listed.status_code == 200
    names = [row["name"] for row in listed.data["results"]] if isinstance(listed.data, dict) and "results" in listed.data else [row["name"] for row in listed.data]
    assert "Cached Widget" in names
    patched = tenant_a.client.patch(
        f"/api/v1/products/{product.id}/",
        {"name": "Fresh Widget"},
        format="json",
    )
    assert patched.status_code == 200, patched.data
    assert cache.get(f"masters:products:{tenant_a.company.pk}") is None
    listed2 = tenant_a.client.get("/api/v1/products/")
    names2 = [row["name"] for row in listed2.data["results"]] if isinstance(listed2.data, dict) and "results" in listed2.data else [row["name"] for row in listed2.data]
    assert "Fresh Widget" in names2
    assert "Cached Widget" not in names2


@pytest.mark.no_invariant_check  # deliberately mutates a document amount to trigger rematch
def test_r041_rematch_matched_when_gstin_or_amount_changes(tenant_a):
    company = tenant_a.company
    supplier = make_supplier(company, gstin="29AAAAA0000A1Z5")
    inv = PurchaseInvoice.objects.create(
        company=company,
        supplier=supplier,
        number="PI-REMATCH-1",
        invoice_date=date(2026, 4, 1),
        status=PurchaseInvoice.Status.COMPLETED,
        taxable_total=Decimal("1000"),
        cgst_total=Decimal("90"),
        sgst_total=Decimal("90"),
        grand_total=Decimal("1180"),
    )
    row = Gstr2bIngest.objects.create(
        company=company,
        period="2026-04",
        supplier_gstin="29AAAAA0000A1Z5",
        invoice_number="PI-REMATCH-1",
        invoice_date=date(2026, 4, 1),
        taxable_value=Decimal("1000"),
        cgst=Decimal("90"),
        sgst=Decimal("90"),
        match_status=Gstr2bIngest.MatchStatus.MATCHED,
        purchase_invoice=inv,
    )
    match_gstr2b_to_purchases(company, "2026-04", persist=True)
    row.refresh_from_db()
    assert row.match_status == Gstr2bIngest.MatchStatus.MATCHED

    supplier.gstin = "29BBBBB0000B1Z5"
    supplier.save(update_fields=["gstin"])
    match_gstr2b_to_purchases(company, "2026-04", persist=True)
    row.refresh_from_db()
    assert row.match_status != Gstr2bIngest.MatchStatus.MATCHED

    supplier.gstin = "29AAAAA0000A1Z5"
    supplier.save(update_fields=["gstin"])
    inv.taxable_total = Decimal("1500")
    inv.cgst_total = Decimal("135")
    inv.sgst_total = Decimal("135")
    inv.save(update_fields=["taxable_total", "cgst_total", "sgst_total"])
    row.match_status = Gstr2bIngest.MatchStatus.MATCHED
    row.purchase_invoice = inv
    row.save(update_fields=["match_status", "purchase_invoice"])
    match_gstr2b_to_purchases(company, "2026-04", persist=True)
    row.refresh_from_db()
    assert row.match_status != Gstr2bIngest.MatchStatus.MATCHED


def test_r044_get_daily_summary_does_not_insert(tenant_a):
    assert DailyBusinessSummary.objects.filter(company=tenant_a.company).count() == 0
    resp = tenant_a.client.get("/api/v1/insights/daily-summary/")
    assert resp.status_code == 200
    assert DailyBusinessSummary.objects.filter(company=tenant_a.company).count() == 0
    assert resp.data.get("kpis") == {}


def test_r044_get_health_history_does_not_insert(tenant_a):
    assert BusinessHealthSnapshot.objects.filter(company=tenant_a.company).count() == 0
    resp = tenant_a.client.get("/api/v1/insights/health/history/")
    assert resp.status_code == 200
    assert BusinessHealthSnapshot.objects.filter(company=tenant_a.company).count() == 0


def test_r048_preview_rate_override_writes_no_audit(tenant_a):
    product = make_product(tenant_a.company, sku="OV-1", gst_rate="18")
    before = AuditEvent.objects.filter(company=tenant_a.company).count()
    build_totals_preview(
        company=tenant_a.company,
        party_state="Karnataka",
        party_gstin="",
        data={
            "invoice_date": "2026-04-01",
            "items": [
                {
                    "product": product.id,
                    "quantity": "1",
                    "unit_price": "100",
                    "gst_rate": "5",
                    "rate_override": True,
                    "rate_override_reason": "Preview quote only",
                }
            ],
        },
        products_by_id={product.id: product},
        default_price_attr="selling_price",
        tax_enabled=True,
    )
    after = AuditEvent.objects.filter(company=tenant_a.company).count()
    assert after == before


@override_settings(ENABLE_WHATSAPP_CLOUD=True)
@patch("core.services.whatsapp.requests.post")
def test_r052_cloud_http_400_is_failed_and_passes_locale(mock_post, tenant_a):
    upsert = tenant_a.client.put(
        "/api/v1/integrations/whatsapp/connection/",
        {"token": "tok", "phone_number_id": "111"},
        format="json",
    )
    assert upsert.status_code == 200, upsert.data
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = "template language mismatch"
    mock_post.return_value = mock_resp
    with translation.override("hi"):
        result = send_whatsapp_template(
            "919876543210",
            "invoice_ready",
            ["INV-1"],
            company=tenant_a.company,
        )
    assert result.mode == "failed"
    assert not (result.share_link or "").startswith("https://wa.me/")
    sent_json = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
    assert sent_json["template"]["language"]["code"] == "hi"


def test_r052_language_code_from_locale():
    assert _whatsapp_language_code("en-us") == "en"
    assert _whatsapp_language_code("hi_IN") == "hi"
    with translation.override("hi"):
        assert _whatsapp_language_code() == "hi"


def test_r054_setting_default_warehouse_clears_others(tenant_a):
    company = tenant_a.company
    Warehouse.objects.filter(company=company).update(is_default=False)
    leftover = Warehouse.objects.filter(company=company, code="DEFAULT").first()
    if leftover is None:
        leftover = Warehouse.objects.create(
            company=company, name="Default Godown", code="DEFAULT", is_default=False,
        )
    Warehouse.objects.create(company=company, name="Spare", code="SPARE", is_default=False)
    result = InventoryService.default_warehouse(company)
    assert result.is_default is True
    assert Warehouse.objects.filter(company=company, is_default=True).count() == 1


def test_r056_item_custom_fields_v2_absent_is_false(tenant_a):
    tenant_a.company.feature_flags = {}
    tenant_a.company.save(update_fields=["feature_flags"])
    flags = build_feature_flags(company=tenant_a.company)
    assert flags["item_custom_fields_v2"] is False


@override_settings(ENABLE_MANUFACTURING=True, ENABLE_PAYROLL=True, ENABLE_CRM=True)
def test_r015_empty_and_non_dict_plan_modules_fail_closed(tenant_a):
    """R-015: {} and non-dict plan modules are fail-closed; None still falls back."""
    tenant_a.company.feature_flags = {}
    tenant_a.company.save(update_fields=["feature_flags"])
    # Clear memo so patched plan_modules are re-read.
    if hasattr(tenant_a.company, "_feature_flags_cache"):
        delattr(tenant_a.company, "_feature_flags_cache")

    with patch("billing.services.plan_modules_for_company", return_value={}):
        if hasattr(tenant_a.company, "_feature_flags_cache"):
            delattr(tenant_a.company, "_feature_flags_cache")
        flags = build_feature_flags(company=tenant_a.company)
    assert flags["ENABLE_CRM"] is False
    assert flags["ENABLE_MANUFACTURING"] is False
    assert flags["ENABLE_PAYROLL"] is False

    with patch("billing.services.plan_modules_for_company", return_value=["ENABLE_CRM"]):
        if hasattr(tenant_a.company, "_feature_flags_cache"):
            delattr(tenant_a.company, "_feature_flags_cache")
        flags = build_feature_flags(company=tenant_a.company)
    assert flags["ENABLE_CRM"] is False
    assert flags["ENABLE_MANUFACTURING"] is False

    with patch("billing.services.plan_modules_for_company", return_value=None):
        if hasattr(tenant_a.company, "_feature_flags_cache"):
            delattr(tenant_a.company, "_feature_flags_cache")
        flags = build_feature_flags(company=tenant_a.company)
    # No subscription info → env fallback (legacy_env_only).
    assert flags["ENABLE_CRM"] is True


def test_r015_billing_non_dict_modules_coerced_to_empty():
    from billing.services import plan_modules_for_company

    company = MagicMock()
    company.pk = 1
    sub = MagicMock()
    sub.plan_id = 9
    sub.plan.modules = ["not", "a", "dict"]
    with patch("billing.services.subscription_for_company", return_value=sub):
        assert plan_modules_for_company(company) == {}
    sub.plan.modules = {}
    with patch("billing.services.subscription_for_company", return_value=sub):
        assert plan_modules_for_company(company) == {}
    with patch("billing.services.subscription_for_company", return_value=None):
        assert plan_modules_for_company(company) is None


def test_r036_tax_rate_list_fresh_after_patch(tenant_a):
    created = tenant_a.client.post(
        "/api/v1/masters/tax-rates/",
        {"name": "GST18", "rate": "18"},
        format="json",
    )
    assert created.status_code in (200, 201), created.data
    listed = tenant_a.client.get("/api/v1/masters/tax-rates/")
    assert listed.status_code == 200
    row_id = created.data["id"]
    patched = tenant_a.client.patch(
        f"/api/v1/masters/tax-rates/{row_id}/",
        {"name": "GST18-fresh"},
        format="json",
    )
    assert patched.status_code == 200, patched.data
    assert cache.get(f"masters:tax_rates:{tenant_a.company.pk}") is None
    listed2 = tenant_a.client.get("/api/v1/masters/tax-rates/")
    names = (
        [row["name"] for row in listed2.data["results"]]
        if isinstance(listed2.data, dict) and "results" in listed2.data
        else [row["name"] for row in listed2.data]
    )
    assert "GST18-fresh" in names
