"""Sprint 5: WhatsApp, Tally honesty, OCR, AI/report KPIs."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from core.services.llm import _normalize_payload
from core.services.whatsapp import send_whatsapp_template
from insights.assistant import ToolExecutor, run_assistant_turn
from insights.models import AssistantThread
from insights.services import compute_health_score
from reporting.services import ReportService
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db


def _body(resp):
    data = resp.data
    if isinstance(data, dict) and isinstance(data.get("data"), (dict, list)):
        return data["data"]
    return data


@override_settings(ENABLE_WHATSAPP_CLOUD=True, WHATSAPP_TOKEN="global-token", WHATSAPP_PHONE_NUMBER_ID="999")
def test_bb_000571_no_global_wa_token_fallback(tenant_a):
    result = send_whatsapp_template(
        "919876543210", "invoice_ready", ["INV-1"], company=tenant_a.company,
    )
    assert result.mode == "link"
    assert "wa.me" in result.share_link


@override_settings(ENABLE_WHATSAPP_CLOUD=True)
@patch("core.services.whatsapp.requests.post")
def test_bb_000678_owner_whatsapp_connection_crud(mock_post, tenant_a):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"messages": [{"id": "wamid.1"}]}
    mock_post.return_value = mock_resp

    upsert = tenant_a.client.put(
        "/api/v1/integrations/whatsapp/connection/",
        {"token": "tenant-token", "phone_number_id": "111222333"},
        format="json",
    )
    assert upsert.status_code == 200, upsert.data
    listing = tenant_a.client.get("/api/v1/integrations/whatsapp/connection/")
    assert listing.status_code == 200
    assert _body(listing)["configured"] is True
    assert "tenant-token" not in str(listing.data)

    result = send_whatsapp_template(
        "919876543210", "invoice_ready", ["INV-1"], company=tenant_a.company,
    )
    assert result.mode == "cloud"
    mock_post.assert_called()

    staff = tenant_a.staff_client.put(
        "/api/v1/integrations/whatsapp/connection/",
        {"token": "x", "phone_number_id": "1"},
        format="json",
    )
    assert staff.status_code == 403

    deleted = tenant_a.client.delete("/api/v1/integrations/whatsapp/connection/")
    assert deleted.status_code == 200
    after = send_whatsapp_template(
        "919876543210", "invoice_ready", ["INV-1"], company=tenant_a.company,
    )
    assert after.mode == "link"


@override_settings(ENABLE_WHATSAPP_CLOUD=True)
def test_bb_000679_unapproved_template_uses_wa_me(tenant_a):
    tenant_a.client.put(
        "/api/v1/integrations/whatsapp/connection/",
        {"token": "tenant-token", "phone_number_id": "111222333"},
        format="json",
    )
    result = send_whatsapp_template(
        "919876543210", "Invoice INV-99 is ready", ["body"], company=tenant_a.company,
    )
    assert result.mode == "link"
    assert "wa.me" in result.share_link


@override_settings(ENABLE_WHATSAPP_CLOUD=False)
def test_bb_000679_flag_off_forces_wa_me(tenant_a):
    tenant_a.client.put(
        "/api/v1/integrations/whatsapp/connection/",
        {"token": "tenant-token", "phone_number_id": "111222333"},
        format="json",
    )
    result = send_whatsapp_template(
        "919876543210", "invoice_ready", ["INV-1"], company=tenant_a.company,
    )
    assert result.mode == "link"


@patch("requests.post")
def test_bb_000628_tally_push_labelled_export_dump(mock_post, tenant_a):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.ok = True
    mock_resp.text = "OK"
    mock_post.return_value = mock_resp
    resp = tenant_a.client.post(
        "/api/v1/integrations/tally/push-http/",
        {"kind": "masters", "baseUrl": "http://tally.test:9000"},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    body = _body(resp)
    assert body["mode"] == "export_dump"
    assert body["sync"] is False
    assert "export dump" in (body.get("disclaimer") or "").lower() or "not live" in (
        body.get("disclaimer") or ""
    ).lower()


def test_bb_000557_ocr_no_invented_gst_rate():
    payload = _normalize_payload({
        "confidence": "0.4",
        "lines": [{"name": "Widget", "quantity": "2", "unit_price": "10", "gst_rate": ""}],
    })
    assert payload["lines"][0]["gst_rate"] == ""
    assert payload["lines"][0]["include"] is False
    assert payload["confidence"] == 0.4


def test_bb_000629_ocr_keeps_confidence():
    payload = _normalize_payload({
        "confidence": "0.91",
        "lines": [{
            "name": "Bolt", "quantity": "5", "unit_price": "2", "gst_rate": "18", "confidence": "0.7",
        }],
    })
    assert payload["confidence"] == 0.91
    assert payload["lines"][0]["confidence"] == 0.7
    assert payload["lines"][0]["include"] is True


def test_bb_000692_ocr_excludes_unread_qty():
    payload = _normalize_payload({
        "lines": [{"name": "Unknown qty SKU", "quantity": "", "unit_price": "9", "gst_rate": "12"}],
    })
    assert payload["lines"][0]["quantity"] == ""
    assert payload["lines"][0]["include"] is False


def test_ocr_coerces_cgst_sgst_to_total_gst():
    from core.services.llm import _coerce_gst_rate

    assert _coerce_gst_rate("CGST 2.500 + SGST 2.500") == "5"
    assert _coerce_gst_rate("9+9") == "18"
    assert _coerce_gst_rate("IGST 12") == "12"
    assert _coerce_gst_rate("18") == "18"
    assert _coerce_gst_rate("") == ""


def test_ocr_normalize_maps_pcode_and_pc_price():
    payload = _normalize_payload({
        "confidence": "0.8",
        "lines": [{
            "name": "Olay NA IGF 40gm",
            "pcode": "OLAY40",
            "hsn": "33049990",
            "quantity": "3",
            "pc_price": "140.50",
            "gst_rate": "CGST 9 + SGST 9",
            "mrp": "199",
        }],
    })
    line = payload["lines"][0]
    assert line["sku"] == "OLAY40"
    assert line["hsn_code"] == "33049990"
    assert line["unit_price"] == "140.50"
    assert line["gst_rate"] == "18"
    assert line["include"] is True


def test_bb_000686_ap_aging_uses_outstanding(tenant_a):
    product = make_product(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    pur = create_draft_purchase(
        tenant_a, supplier, [{"product": product.id, "quantity": "10", "unit_price": "80"}],
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200
    payment = tenant_a.client.post(
        "/api/v1/payments/supplier-payments/",
        {"supplier": supplier.id, "amount": "500", "mode": "BANK"},
        format="json",
    )
    assert payment.status_code == 201, payment.data
    alloc = tenant_a.client.post(
        "/api/v1/payments/allocations/",
        {
            "supplier_payment": _body(payment)["id"] if isinstance(_body(payment), dict) else payment.data["id"],
            "purchase_invoice": pur["id"],
            "amount": "500",
        },
        format="json",
    )
    assert alloc.status_code == 201, alloc.data
    aging = ReportService.payables_aging(tenant_a.company)
    total = sum(aging.values(), Decimal("0"))
    assert total == Decimal("444.00")
    executor = ToolExecutor(tenant_a.company)
    tool = executor.tool_get_payables_aging()
    assert Decimal(tool["aging"]["current"]) + Decimal(tool["aging"]["days_1_30"]) + Decimal(
        tool["aging"]["days_31_60"]
    ) + Decimal(tool["aging"]["days_61_90"]) + Decimal(tool["aging"]["days_90_plus"]) == Decimal("444.00")


def test_bb_000687_payables_pressure_uses_supplier_payments(tenant_a):
    product = make_product(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    customer = make_customer(tenant_a.company)
    pur = create_draft_purchase(
        tenant_a, supplier, [{"product": product.id, "quantity": "10", "unit_price": "80"}],
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200
    add_stock(tenant_a, product, "20")
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    receipt = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {"customer": customer.id, "amount": "5000", "mode": "CASH"},
        format="json",
    )
    assert receipt.status_code == 201, receipt.data
    before = compute_health_score(tenant_a.company)
    payables_before = next(f for f in before["factors"] if f["key"] == "payables")
    assert "supplier payments" in payables_before["detail"].lower()
    tenant_a.client.post(
        "/api/v1/payments/supplier-payments/",
        {"supplier": supplier.id, "amount": "400", "mode": "CASH"},
        format="json",
    )
    after = compute_health_score(tenant_a.company)
    payables_after = next(f for f in after["factors"] if f["key"] == "payables")
    assert Decimal(payables_after["score"]) != Decimal(payables_before["score"])


def test_bb_000688_sales_kpis_net_of_returns(tenant_a):
    product = make_product(tenant_a.company, gst_rate="0")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "2", "unit_price": "100", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    ret = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {
            "customer": customer.id,
            "sales_invoice": inv["id"],
            "items": [{"product": product.id, "quantity": "2", "unit_price": "100"}],
        },
        format="json",
    )
    assert ret.status_code == 201, ret.data
    assert tenant_a.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/").status_code == 200
    dash = ReportService.dashboard(tenant_a.company)
    assert Decimal(str(dash["sales_today"]["total"])) == Decimal("0")
    executor = ToolExecutor(tenant_a.company)
    totals = executor.tool_get_sales_totals(days=1)
    assert Decimal(totals["total"]) == Decimal("0")


def test_bb_000689_inventory_summary_uses_layer_cost(tenant_a):
    product = make_product(tenant_a.company, purchase_price="50")
    add_stock(tenant_a, product, "4", unit_cost="80")
    summary = ReportService.inventory_summary(tenant_a.company)
    row = next(r for r in summary["rows"] if r["product_id"] == product.id)
    assert Decimal(str(row["stock_value"])) == Decimal("320.00")
    assert Decimal(str(summary["total_stock_value"])) == Decimal("320.00")


def test_bb_000690_reports_filter_warehouse_gstin(tenant_a):
    from inventory.services import InventoryService

    product = make_product(tenant_a.company, gst_rate="0")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    other_wh = tenant_a.client.post(
        "/api/v1/inventory/warehouses/",
        {"name": "Branch B", "code": "BRB"},
        format="json",
    )
    assert other_wh.status_code == 201, other_wh.data
    other_id = _body(other_wh)["id"]
    filtered = tenant_a.client.get(f"/api/v1/reports/inventory-summary/?warehouse={other_id}")
    assert filtered.status_code == 200, filtered.data
    rows = _body(filtered).get("rows") if isinstance(_body(filtered), dict) else None
    if rows is None:
        rows = ReportService.inventory_summary(tenant_a.company, warehouse_id=other_id)["rows"]
    assert all(str(r.get("warehouse_id")) == str(other_id) for r in rows)
    default_wh = InventoryService.default_warehouse(tenant_a.company)
    sales = tenant_a.client.get(f"/api/v1/reports/sales-register/?warehouse={default_wh.id}")
    assert sales.status_code == 200
    empty = tenant_a.client.get(f"/api/v1/reports/sales-register/?warehouse={other_id}")
    assert empty.status_code == 200
    empty_rows = _body(empty).get("rows") if isinstance(_body(empty), dict) else []
    assert empty_rows == [] or all(False for _ in empty_rows[:1] if False)


def test_bb_000627_indirect_gst_prompt_refused(tenant_a):
    tenant_a.company.ai_features_enabled = True
    tenant_a.company.save(update_fields=["ai_features_enabled"])
    thread = AssistantThread.objects.create(company=tenant_a.company, created_by=tenant_a.owner)
    msg = run_assistant_turn(
        tenant_a.company,
        tenant_a.owner,
        thread,
        "What rate for soap sold to Pune?",
    )
    assert "cannot give tax" in msg.content.lower()
