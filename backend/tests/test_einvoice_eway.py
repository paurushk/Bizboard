"""Phase 2 e-Invoice / e-Way payload foundations (no NIC HTTP)."""

from decimal import Decimal

import pytest

from sales.models import SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db

GSTIN_CO = "29ABCDE1234F1ZW"
GSTIN_CU = "29AABCU9603R1ZJ"


def _gst_ready_company(tenant):
    tenant.company.gstin = GSTIN_CO
    tenant.company.address = "123 MG Road"
    tenant.company.city = "Bengaluru"
    tenant.company.pincode = "560001"
    tenant.company.save(update_fields=["gstin", "address", "city", "pincode"])


def _gst_ready_customer(company, **kwargs):
    return make_customer(
        company,
        gstin=GSTIN_CU,
        billing_address="45 Residency Road, Bengaluru 560001",
        state="Karnataka",
        **kwargs,
    )


def _complete_gst_invoice(tenant, *, product_kwargs=None, customer_kwargs=None):
    _gst_ready_company(tenant)
    product = make_product(
        tenant.company,
        hsn_code="3004",
        **(product_kwargs or {}),
    )
    add_stock(tenant, product, "10")
    customer = _gst_ready_customer(tenant.company, **(customer_kwargs or {}))
    inv = create_draft_invoice(tenant, customer, [
        {"product": product.id, "quantity": "2", "unit_price": "100"},
    ])
    resp = tenant.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 200, resp.data
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    invoice.transport_distance_km = 120
    invoice.save(update_fields=["transport_distance_km"])
    resp.data["transport_distance_km"] = 120
    return resp.data, product, customer


def test_prepare_einvoice_fails_without_gstin(tenant_a):
    product = make_product(tenant_a.company, hsn_code="3004")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company, billing_address="45 Residency Road")
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100"},
    ])
    tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")

    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/prepare-einvoice/")
    assert resp.status_code == 400
    assert "GSTIN" in str(resp.data)

    invoice = SalesInvoice.objects.get(pk=inv["id"])
    assert invoice.einvoice_status == SalesInvoice.EInvoiceStatus.FAILED
    assert invoice.einvoice_error


def test_prepare_einvoice_fails_without_hsn(tenant_a):
    _gst_ready_company(tenant_a)
    product = make_product(tenant_a.company, hsn_code="")
    add_stock(tenant_a, product, "10")
    customer = _gst_ready_customer(tenant_a.company)
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100"},
    ])
    tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")

    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/prepare-einvoice/")
    assert resp.status_code == 400
    assert "HSN" in str(resp.data)


def test_prepare_einvoice_succeeds_for_complete_gst_invoice(tenant_a):
    data, _, _ = _complete_gst_invoice(tenant_a)

    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{data['id']}/prepare-einvoice/")
    assert resp.status_code == 200, resp.data
    assert resp.data["einvoice_status"] == "READY"
    assert "payload" in resp.data

    payload = resp.data["payload"]
    for key in ("Version", "TranDtls", "DocDtls", "SellerDtls", "BuyerDtls", "ItemList"):
        assert key in payload, f"missing top-level key {key}"
    assert payload["DocDtls"]["No"] == data["number"]
    assert payload["SellerDtls"]["Gstin"] == GSTIN_CO
    assert payload["BuyerDtls"]["Gstin"] == GSTIN_CU
    assert payload["ItemList"][0]["HsnCd"] == "3004"


def test_mark_einvoice_generated_requires_owner(tenant_a):
    data, _, _ = _complete_gst_invoice(tenant_a)
    tenant_a.company.einvoice_enabled = True
    tenant_a.company.save(update_fields=["einvoice_enabled"])
    tenant_a.client.post(f"/api/v1/sales/invoices/{data['id']}/prepare-einvoice/")

    resp = tenant_a.staff_client.post(
        f"/api/v1/sales/invoices/{data['id']}/mark-einvoice-generated/",
        {"irn": "abc123", "ack_no": "ACK1"},
        format="json",
    )
    assert resp.status_code == 403

    resp = tenant_a.client.post(
        f"/api/v1/sales/invoices/{data['id']}/mark-einvoice-generated/",
        {"irn": "abc123irn", "ack_no": "ACK001", "reason": "Manual portal filing"},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    assert resp.data["einvoice_status"] == "MANUAL_IRN"
    assert resp.data["irn"] == "abc123irn"
    assert resp.data["ack_no"] == "ACK001"


def test_mark_einvoice_generated_requires_reason(tenant_a):
    data, _, _ = _complete_gst_invoice(tenant_a)
    tenant_a.company.einvoice_enabled = True
    tenant_a.company.save(update_fields=["einvoice_enabled"])
    resp = tenant_a.client.post(
        f"/api/v1/sales/invoices/{data['id']}/mark-einvoice-generated/",
        {"irn": "abc123irn", "ack_no": "ACK001"},
        format="json",
    )
    assert resp.status_code == 400
    assert "reason" in str(resp.data).lower()


def test_mark_einvoice_generated_requires_enabled(tenant_a):
    data, _, _ = _complete_gst_invoice(tenant_a)
    tenant_a.company.einvoice_enabled = False
    tenant_a.company.save(update_fields=["einvoice_enabled"])
    resp = tenant_a.client.post(
        f"/api/v1/sales/invoices/{data['id']}/mark-einvoice-generated/",
        {"irn": "abc123irn", "ack_no": "ACK001", "reason": "test"},
        format="json",
    )
    assert resp.status_code == 400
    assert "not enabled" in str(resp.data).lower()


def test_prepare_eway_from_invoice(tenant_a):
    data, _, _ = _complete_gst_invoice(tenant_a)

    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{data['id']}/prepare-eway/")
    assert resp.status_code == 200, resp.data
    assert resp.data["eway_status"] == "READY"
    assert resp.data["payload"]["docType"] == "INV"
    assert resp.data["payload"]["fromGstin"] == GSTIN_CO


def test_prepare_eway_from_challan(tenant_a):
    _gst_ready_company(tenant_a)
    product = make_product(tenant_a.company, hsn_code="3004")
    add_stock(tenant_a, product, "10")
    customer = _gst_ready_customer(tenant_a.company)

    payload = {
        "customer": customer.id,
        "challan_date": "2026-08-02",
        "vehicle_number": "KA01AB1234",
        "transporter_name": "FastTrans",
        "transport_distance_km": 80,
        "items": [{"product": product.id, "quantity": "1", "unit_price": "100"}],
    }
    create_resp = tenant_a.client.post("/api/v1/sales/delivery-challans/", payload, format="json")
    assert create_resp.status_code == 201, create_resp.data
    challan_id = create_resp.data["id"]
    tenant_a.client.post(f"/api/v1/sales/delivery-challans/{challan_id}/complete/")

    resp = tenant_a.client.post(f"/api/v1/sales/delivery-challans/{challan_id}/prepare-eway/")
    assert resp.status_code == 200, resp.data
    assert resp.data["eway_status"] == "READY"
    assert resp.data["payload"]["docType"] == "CHL"
    assert resp.data["payload"]["vehicleNo"] == "KA01AB1234"
    assert resp.data["payload"]["transporterName"] == "FastTrans"


def test_mark_eway_generated_on_invoice(tenant_a):
    data, _, _ = _complete_gst_invoice(tenant_a)
    tenant_a.company.eway_enabled = True
    tenant_a.company.save(update_fields=["eway_enabled"])
    tenant_a.client.post(f"/api/v1/sales/invoices/{data['id']}/prepare-eway/")

    resp = tenant_a.client.post(
        f"/api/v1/sales/invoices/{data['id']}/mark-eway-generated/",
        {"eway_bill_no": "EWB123456", "reason": "Manual portal filing"},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    assert resp.data["eway_status"] == "MANUAL_EWB"
    assert resp.data["eway_bill_no"] == "EWB123456"

    invoice = SalesInvoice.objects.get(pk=data["id"])
    assert invoice.eway_status == SalesInvoice.EwayStatus.MANUAL_EWB


def test_prepare_eway_rejects_missing_buyer_pincode(tenant_a):
    data, _, customer = _complete_gst_invoice(tenant_a)
    customer.billing_address = "45 Residency Road"
    customer.shipping_address = ""
    customer.save(update_fields=["billing_address", "shipping_address"])
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{data['id']}/prepare-eway/")
    assert resp.status_code == 400
    assert "pincode" in str(resp.data).lower()


def test_prepare_eway_uses_decimal_strings_and_uqc(tenant_a):
    data, _, _ = _complete_gst_invoice(tenant_a)
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{data['id']}/prepare-eway/")
    assert resp.status_code == 200, resp.data
    payload = resp.data["payload"]
    assert payload["toPincode"] == 560001
    assert isinstance(payload["totalValue"], str)
    assert isinstance(payload["itemList"][0]["quantity"], str)
    assert payload["itemList"][0]["qtyUnit"] in ("NOS", "PCS", "OTH") or len(
        payload["itemList"][0]["qtyUnit"]
    ) >= 2


def test_einvoice_valdtls_before_tax_discount_zero(tenant_a):
    from sales.einvoice_payload import build_einvoice_payload

    _gst_ready_company(tenant_a)
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save(update_fields=["state"])
    product = make_product(tenant_a.company, hsn_code="3004")
    add_stock(tenant_a, product, "10")
    customer = _gst_ready_customer(tenant_a.company)
    create = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": customer.id,
            "invoice_type": "GST",
            "invoice_date": "2026-08-02",
            "invoice_discount": "50",
            "invoice_discount_mode": "BEFORE_TAX",
            "auto_round_off": False,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18"}],
        },
        format="json",
    )
    assert create.status_code == 201, create.data
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{create.data['id']}/complete/")
    assert done.status_code == 200, done.data
    invoice = SalesInvoice.objects.get(pk=create.data["id"])
    payload = build_einvoice_payload(invoice)
    assert payload["ValDtls"]["Discount"] == "0.00"
    assert payload["TranDtls"]["SupTyp"] == "B2B"
    assert payload["TranDtls"]["RegRev"] == "N"
    ass = Decimal(payload["ValDtls"]["AssVal"])
    tax = (
        Decimal(payload["ValDtls"]["CgstVal"])
        + Decimal(payload["ValDtls"]["SgstVal"])
        + Decimal(payload["ValDtls"]["IgstVal"])
    )
    rnd = Decimal(payload["ValDtls"]["RndOffAmt"])
    oth = Decimal(payload["ValDtls"]["OthChrg"])
    disc = Decimal(payload["ValDtls"]["Discount"])
    tot = Decimal(payload["ValDtls"]["TotInvVal"])
    assert ass + tax + rnd + oth - disc == tot
