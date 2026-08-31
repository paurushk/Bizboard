"""W0-04 / W0-05 / W0-07 / D-02 / A-01 / B-01 / B-02 remaining GATE:eng slices."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.test import override_settings
from rest_framework.response import Response

from accounting.services import seed_chart_of_accounts
from core.exceptions import BusinessRuleError
from core.help_codes import HelpCode
from core.idempotency import get_record, wrap_idempotent
from core.services.document_numbers import DocumentNumberService, series_identity
from core.services.gsp_adapters import LiveIrpAdapter, LiveGstrFilingAdapter, reject_placeholder_gsp_credentials
from core.services.gsp_secrets import encrypt_gsp_credentials
from integrations.tally.adapter import DISCLAIMER, parse_tally_masters_rows
from ledgers.services import LedgerService
from reporting.gst_returns import build_gstr9
from sales.models import SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def test_w0_04_gstin_company_stray_caller_uses_fy_series(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.save(update_fields=["gstin"])
    gk, fy, _on = series_identity(tenant_a.company)
    assert gk == "29ABCDE1234F1ZW"
    assert fy
    n = DocumentNumberService.next_number(tenant_a.company, "SALES_INVOICE")
    assert fy.replace("-", "")[-4:] in n.replace("-", "") or fy.split("-")[0][-2:] in n
    assert gk[-4:] in n or n.startswith("INV-")


def test_w0_04_no_gstin_keeps_legacy_unscoped_series(tenant_a):
    assert DocumentNumberService.next_number(tenant_a.company, "SALES_INVOICE") == "INV-00001"


def test_w0_04_cancelled_invoice_on_register_keeps_number(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    draft = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100"}]
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert done.status_code == 200, done.data
    number = done.data["number"]
    cancel = tenant_a.client.post(
        f"/api/v1/sales/invoices/{draft['id']}/cancel/",
        {"reason": "Duplicate bill"},
        format="json",
    )
    assert cancel.status_code == 200, cancel.data
    inv = SalesInvoice.objects.get(pk=draft["id"])
    assert inv.status == SalesInvoice.Status.CANCELLED
    assert inv.number == number
    fy = DocumentNumberService.peek(tenant_a.company, "SALES_INVOICE")["fy_label"] or "2026-27"
    # Unscoped series still uses calendar FY for the register filter via invoice_date.
    from core.services.document_numbers import gst_fy_label_for

    fy = gst_fy_label_for(inv.invoice_date)
    resp = tenant_a.client.get("/api/v1/reports/cancelled-document-numbers/", {"fy": fy})
    assert resp.status_code == 200, resp.data
    rows = resp.data.get("rows") or (resp.data.get("data") or {}).get("rows") or []
    if isinstance(resp.data.get("data"), list):
        rows = resp.data["data"]
    assert any(r.get("number") == number for r in rows)
    csv_resp = tenant_a.client.get(
        "/api/v1/reports/cancelled-document-numbers/", {"fy": fy, "format": "csv"}
    )
    assert csv_resp.status_code == 200
    assert number.encode() in csv_resp.content


def test_w0_04_fy_restart_warning_text(tenant_a):
    from core.models import DocumentSeries

    DocumentNumberService.next_number(
        tenant_a.company, "SALES_INVOICE", gstin="29ABCDE1234F1ZW", on_date=date(2025, 5, 1)
    )
    warn = DocumentNumberService.fy_restart_warning(
        tenant_a.company,
        "SALES_INVOICE",
        gstin_key="29ABCDE1234F1ZW",
        fy_label="2026-27",
    )
    DocumentSeries.objects.get_or_create(
        company=tenant_a.company,
        doc_type="SALES_INVOICE",
        gstin_key="29ABCDE1234F1ZW",
        fy_label="2026-27",
        defaults={"prefix": "INV-2627"},
    )
    warn = DocumentNumberService.fy_restart_warning(
        tenant_a.company,
        "SALES_INVOICE",
        gstin_key="29ABCDE1234F1ZW",
        fy_label="2026-27",
    )
    assert warn and "starts at 1" in warn


def test_w0_05_deterministic_4xx_stored(tenant_a):
    req = SimpleNamespace(headers={"Idempotency-Key": "det-4xx"})
    calls = []

    def build():
        calls.append(1)
        raise BusinessRuleError("limit", code=HelpCode.CREDIT_LIMIT_EXCEEDED)

    resp = wrap_idempotent(request=req, company=tenant_a.company, scope="t_det", build=build)
    assert resp.status_code == 400
    assert len(calls) == 1
    rec = get_record(company=tenant_a.company, scope="t_det", raw_key="det-4xx")
    assert rec is not None and rec.status_code == 400
    resp2 = wrap_idempotent(request=req, company=tenant_a.company, scope="t_det", build=build)
    assert resp2.status_code == 400
    assert len(calls) == 1


def test_w0_05_transient_closed_period_released(tenant_a):
    req = SimpleNamespace(headers={"Idempotency-Key": "tr-4xx"})
    calls = []

    def build():
        calls.append(1)
        raise BusinessRuleError("locked", code=HelpCode.CLOSED_PERIOD)

    with pytest.raises(BusinessRuleError):
        wrap_idempotent(request=req, company=tenant_a.company, scope="t_tr", build=build)
    rec = get_record(company=tenant_a.company, scope="t_tr", raw_key="tr-4xx")
    assert rec is None
    assert len(calls) == 1

    def ok():
        calls.append(1)
        return Response({"id": 9}, status=200)

    resp = wrap_idempotent(request=req, company=tenant_a.company, scope="t_tr", build=ok)
    assert resp.status_code == 200
    assert len(calls) == 2


def test_w0_05_confirm_409s_are_released(tenant_a):
    from core.exceptions import CompanyRequired, GstinTotalChanged, StockCountConflict

    req = SimpleNamespace(headers={"Idempotency-Key": "confirm-409"})
    calls = []

    def build():
        calls.append(1)
        raise GstinTotalChanged(
            {"grand_total": "100"}, {"grand_total": "118"}, []
        )

    with pytest.raises(GstinTotalChanged):
        wrap_idempotent(request=req, company=tenant_a.company, scope="t_c9", build=build)
    assert get_record(company=tenant_a.company, scope="t_c9", raw_key="confirm-409") is None

    def company_pick():
        calls.append(1)
        raise CompanyRequired([])

    req2 = SimpleNamespace(headers={"Idempotency-Key": "co-req"})
    with pytest.raises(CompanyRequired):
        wrap_idempotent(request=req2, company=tenant_a.company, scope="t_c9", build=company_pick)
    assert get_record(company=tenant_a.company, scope="t_c9", raw_key="co-req") is None

    def stock_drift():
        calls.append(1)
        raise StockCountConflict([{"sku": "A"}])

    req3 = SimpleNamespace(headers={"Idempotency-Key": "stk"})
    with pytest.raises(StockCountConflict):
        wrap_idempotent(request=req3, company=tenant_a.company, scope="t_c9", build=stock_drift)
    assert get_record(company=tenant_a.company, scope="t_c9", raw_key="stk") is None
    assert len(calls) == 3


def test_w0_05_post_commit_500_stored(tenant_a):
    req = SimpleNamespace(headers={"Idempotency-Key": "five-xx"})
    calls = []

    def build():
        calls.append(1)
        return Response({"detail": "downstream"}, status=500)

    resp = wrap_idempotent(request=req, company=tenant_a.company, scope="t_5", build=build)
    assert resp.status_code == 500
    resp2 = wrap_idempotent(request=req, company=tenant_a.company, scope="t_5", build=build)
    assert resp2.status_code == 500
    assert len(calls) == 1


def test_w0_07_outstanding_nets_advances_and_foots_statement(tenant_a):
    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(company, tenant_a.owner)
    product = make_product(company)
    add_stock(tenant_a, product, "10")
    customer = make_customer(company)
    draft = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "1000"}]
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert done.status_code == 200, done.data
    rec = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {"customer": customer.id, "amount": "400", "mode": "CASH"},
        format="json",
    )
    assert rec.status_code == 201, rec.data
    outstanding = LedgerService.customer_outstanding(company, customer)
    statement = LedgerService.customer_statement(company, customer)
    closing = statement[-1]["balance"] if statement else Decimal("0")
    assert outstanding == closing
    inv_total = Decimal(str(done.data["grand_total"]))
    assert outstanding == inv_total - Decimal("400.00")
    company.outstanding_basis = company.OutstandingBasis.DOCUMENTS_ALWAYS
    company.save(update_fields=["outstanding_basis"])
    docs = LedgerService.customer_outstanding(company, customer)
    assert docs == inv_total


def test_d02_tally_disclaimer_is_not_live_sync():
    assert "Tally sync" not in DISCLAIMER
    preview = parse_tally_masters_rows(
        [{"entity_type": "customer", "name": "A", "opening_outstanding": "10"}]
    )
    assert preview["summary"]["records"] >= 1
    assert preview["summary"]["valid"] == 1
    assert preview["summary"]["errors"] == 0


def test_d02_restore_refuses_unbacked_rows(tenant_a):
    from accounts.tenant_backup import restore_destroy_in_place, unbacked_live_counts
    from sales.models import Quotation

    Quotation.objects.create(
        company=tenant_a.company,
        customer=make_customer(tenant_a.company),
        quotation_date=date(2026, 8, 1),
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    payload = {"source_company_id": tenant_a.company.pk, "sales_invoices": []}
    extra = unbacked_live_counts(tenant_a.company, payload)
    assert extra.get("quotations", 0) >= 1
    with pytest.raises(BusinessRuleError, match="confirm_destroy_unbacked"):
        restore_destroy_in_place(
            company=tenant_a.company, payload=payload, owner=tenant_a.owner
        )


def test_d02_restore_refuses_unbacked_invoices(tenant_a):
    from accounts.tenant_backup import restore_destroy_in_place, unbacked_live_counts

    product = make_product(tenant_a.company)
    customer = make_customer(tenant_a.company)
    create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100"}]
    )
    extra = unbacked_live_counts(
        tenant_a.company, {"sales_invoices": [], "quotations": [], "customers": [], "products": []}
    )
    assert extra.get("sales_invoices", 0) >= 1
    with pytest.raises(BusinessRuleError, match="confirm_destroy_unbacked"):
        restore_destroy_in_place(
            company=tenant_a.company,
            payload={"source_company_id": tenant_a.company.pk, "sales_invoices": []},
            owner=tenant_a.owner,
        )


def test_a01_push_token_patch(tenant_a):
    resp = tenant_a.client.patch("/api/v1/auth/me/", {"pushToken": "tok-android-1"}, format="json")
    assert resp.status_code == 200, resp.data
    tenant_a.owner.refresh_from_db()
    assert tenant_a.owner.push_token == "tok-android-1"


def test_a01_push_token_patch_without_company(db):
    from accounts.models import User
    from rest_framework.test import APIClient

    user = User.objects.create_user(
        email="push-solo@example.test", password="StrongPass123!", full_name="Solo"
    )
    client = APIClient()
    client.force_authenticate(user=user)
    resp = client.patch("/api/v1/auth/me/", {"pushToken": "pre-company"}, format="json")
    assert resp.status_code == 200, resp.data
    user.refresh_from_db()
    assert user.push_token == "pre-company"


def test_d02_recon_stock_fails_when_qty_missing(tenant_a):
    from integrations.tally.adapter import _post_commit_recon

    recon = _post_commit_recon(
        tenant_a.company,
        {"products": [{"sku": "MISSING", "opening_qty": "10"}]},
        {},
    )
    assert recon["stock"]["pass"] is False
    assert recon["stock"]["expected"] == "10"


def test_b02_snapshot_hash_ignores_gsp_upload(tenant_a):
    from reporting.gst_returns import content_hash, persist_snapshot

    payload = {"return_type": "GSTR-1", "totals": {"outward_taxable": "0"}, "builder_version": "test"}
    snap = persist_snapshot(
        tenant_a.company,
        "GSTR-1",
        "2026-04",
        {**payload, "gsp_upload": {"ack": "should-not-hash"}},
        user=tenant_a.owner,
    )
    assert snap.content_hash == content_hash(payload)
    assert "gsp_upload" not in (snap.payload or {})


def test_b02_gstr9_is_unsupported_worksheet(tenant_a):
    payload = build_gstr9(tenant_a.company, "2026-27")
    assert payload["supported"] is False
    assert "books worksheet, not filing pack" in (payload.get("watermark") or "").lower()
    assert "books worksheet, not filing pack" in (payload.get("disclaimer") or "").lower()


@override_settings(GSP_LIVE_ENABLED=True, GSP_CERTIFIED=True, GSP_LIVE_BASE_URL="https://gsp.example")
def test_b01_placeholder_secrets_do_not_http(tenant_a, monkeypatch):
    tenant_a.company.gsp_provider = "cleartax"
    tenant_a.company.gsp_credentials_encrypted = encrypt_gsp_credentials(
        {"username": "AAAA", "password": "AAAAAAAA"}
    )
    tenant_a.company.save(update_fields=["gsp_provider", "gsp_credentials_encrypted"])
    called = []
    monkeypatch.setattr(
        "core.services.gsp_adapters._http_json",
        lambda *a, **k: called.append(1) or {},
    )
    adapter = LiveIrpAdapter(tenant_a.company)
    with pytest.raises(BusinessRuleError, match="Placeholder"):
        adapter.submit({})
    assert called == []


@override_settings(GSP_LIVE_ENABLED=True, GSP_CERTIFIED=True, DJANGO_ENV="production", GSP_LIVE_BASE_URL="")
def test_b02_live_gstr_fail_closed_without_url(tenant_a):
    tenant_a.company.gsp_provider = "cleartax"
    tenant_a.company.gsp_credentials_encrypted = encrypt_gsp_credentials(
        {"username": "real-user", "password": "real-secret-value"}
    )
    tenant_a.company.save(update_fields=["gsp_provider", "gsp_credentials_encrypted"])
    adapter = LiveGstrFilingAdapter(tenant_a.company)
    with pytest.raises(BusinessRuleError):
        adapter.upload_gstr1({"period": "2026-04"})


def test_reject_placeholder_helper():
    with pytest.raises(BusinessRuleError):
        reject_placeholder_gsp_credentials({"key": "aaaaaaaa"})
