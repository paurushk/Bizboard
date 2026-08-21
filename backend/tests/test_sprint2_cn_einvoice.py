"""Sprint 2: CN cap/freeze/return copy + IRN/e-way honesty."""

from decimal import Decimal
import pytest
from django.test import override_settings
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.services.gsp_adapters import LiveIrpAdapter, get_irp_adapter
from payments.services import PaymentService
from sales.einvoice_payload import build_einvoice_payload, build_einvoice_payload_from_note
from sales.eway_payload import build_eway_payload_from_invoice
from sales.models import SalesCreditNote, SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def test_bb_000648_cn_allowed_after_full_receipt(tenant_a):
    product = make_product(tenant_a.company, sku="PAID-CN")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "500", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    receipt = PaymentService.create_receipt(
        company=tenant_a.company, customer=customer, amount=Decimal("500"), mode="CASH", user=tenant_a.owner,
    )
    PaymentService.allocate_receipt(receipt=receipt, sales_invoice=invoice, amount=Decimal("500"), user=tenant_a.owner)
    cn = tenant_a.client.post(
        "/api/v1/sales/credit-notes/",
        {
            "customer": customer.id,
            "sales_invoice": invoice.id,
            "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "500", "gst_rate": "0"}],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    done = tenant_a.client.post(f"/api/v1/sales/credit-notes/{cn.data['id']}/complete/")
    assert done.status_code == 200, done.data


def test_bb_000649_cn_freezes_tax_split_from_invoice(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    product = make_product(tenant_a.company, sku="FRZ-1", hsn_code="1001")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, state="Karnataka", gstin="29AABCU9603R1ZJ")
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    customer.state = "Maharashtra"
    customer.gstin = "27AABCU9603R1ZN"
    customer.save()
    cn = tenant_a.client.post(
        "/api/v1/sales/credit-notes/",
        {
            "customer": customer.id,
            "sales_invoice": inv["id"],
            "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    note = SalesCreditNote.objects.get(pk=cn.data["id"])
    assert note.igst_total == Decimal("0.00")
    assert note.cgst_total + note.sgst_total > 0


def test_bb_000663_auto_return_cn_copies_discount(tenant_a):
    product = make_product(tenant_a.company, sku="RET-CN")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    created = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": customer.id,
            "invoice_type": "NON_GST",
            "invoice_discount": "20",
            "invoice_discount_mode": "AFTER_TAX",
            "auto_round_off": False,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "200", "gst_rate": "0"}],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{created.data['id']}/complete/").status_code == 200
    ret = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {
            "customer": customer.id,
            "sales_invoice": created.data["id"],
            "items": [{"product": product.id, "quantity": "1", "unit_price": "200"}],
        },
        format="json",
    )
    assert ret.status_code == 201, ret.data
    done = tenant_a.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/")
    assert done.status_code == 200, done.data
    note = SalesCreditNote.objects.get(sales_return_id=ret.data["id"])
    assert note.invoice_discount == Decimal("20.00")


def test_bb_000647_note_irn_builder_crn_precdoc(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.pincode = "560001"
    tenant_a.company.address = "1 MG Road"
    tenant_a.company.city = "Bengaluru"
    tenant_a.company.save()
    product = make_product(tenant_a.company, sku="IRN-1", hsn_code="1001")
    add_stock(tenant_a, product, "5")
    customer = make_customer(
        tenant_a.company,
        gstin="29AABCU9603R1ZJ",
        state="Karnataka",
        billing_address="2 Residency 560002",
    )
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18", "cess_rate": "1"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    invoice.number = invoice.number or "INV-IRN-1"
    invoice.irn = "IRN-SOURCE"
    invoice.save()
    cn = tenant_a.client.post(
        "/api/v1/sales/credit-notes/",
        {
            "customer": customer.id,
            "sales_invoice": invoice.id,
            "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18", "cess_rate": "1"}],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    assert tenant_a.client.post(f"/api/v1/sales/credit-notes/{cn.data['id']}/complete/").status_code == 200
    note = SalesCreditNote.objects.get(pk=cn.data["id"])
    payload = build_einvoice_payload_from_note(note)
    assert payload["DocDtls"]["Typ"] == "CRN"
    assert payload["PrecDocDtls"][0]["InvNo"] == invoice.number
    assert payload["ItemList"][0]["CesRt"] == "1.00"


def test_bb_000639_seller_gstin_from_stamp(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.pincode = "560001"
    tenant_a.company.address = "1 MG Road"
    tenant_a.company.save()
    product = make_product(tenant_a.company, sku="STAMP-1", hsn_code="1001")
    add_stock(tenant_a, product, "2")
    customer = make_customer(
        tenant_a.company, gstin="27AABCU9603R1ZN", state="Maharashtra",
        billing_address="Pune 411001",
    )
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    from accounts.models import CompanyGstin

    stamp = CompanyGstin.objects.create(
        company=tenant_a.company, gstin="27AAAAA0000A1Z2", state="Maharashtra", is_primary=False,
    )
    invoice.company_gstin = stamp
    invoice.save(update_fields=["company_gstin"])
    payload = build_einvoice_payload(invoice)
    assert payload["SellerDtls"]["Gstin"] == "27AAAAA0000A1Z2"


def test_bb_000639_seller_stamp_without_company_gstin(tenant_a):
    tenant_a.company.gstin = ""
    tenant_a.company.state = "Karnataka"
    tenant_a.company.pincode = "560001"
    tenant_a.company.address = "1 MG Road"
    tenant_a.company.city = "Bengaluru"
    tenant_a.company.registration_type = tenant_a.company.RegistrationType.REGULAR
    tenant_a.company.save()
    from accounts.models import CompanyGstin

    stamp = CompanyGstin.objects.create(
        company=tenant_a.company,
        gstin="29ABCDE1234F1ZW",
        state="Karnataka",
        address="1 MG Road",
        city="Bengaluru",
        pincode="560001",
        is_primary=True,
    )
    product = make_product(tenant_a.company, sku="STAMP-2", hsn_code="1001")
    add_stock(tenant_a, product, "2")
    customer = make_customer(
        tenant_a.company, gstin="27AABCU9603R1ZN", state="Maharashtra",
        billing_address="Pune 411001",
    )
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18"}],
    )
    tenant_a.client.patch(
        f"/api/v1/sales/invoices/{inv['id']}/",
        {"company_gstin": stamp.id, "items": [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18"}]},
        format="json",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    invoice = SalesInvoice.objects.select_related("company_gstin").get(pk=inv["id"])
    payload = build_einvoice_payload(invoice)
    assert payload["SellerDtls"]["Gstin"] == "29ABCDE1234F1ZW"
    assert invoice.company.gstin == ""


def test_bb_000640_641_642_eway_distance_urp_taxonomy(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.pincode = "560001"
    tenant_a.company.address = "1 MG Road"
    tenant_a.company.city = "Bengaluru"
    tenant_a.company.save()
    customer = make_customer(
        tenant_a.company, gstin="", state="Maharashtra",
        billing_address="Pune 411001",
    )
    product = make_product(tenant_a.company, sku="EWB-1", hsn_code="1001")
    add_stock(tenant_a, product, "2")
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "2000", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    invoice.transport_distance_km = 250
    invoice.sub_supply_type = "3"
    invoice.trans_mode = "2"
    payload = build_eway_payload_from_invoice(invoice)
    assert payload["transDistance"] == "250"
    assert payload["toGstin"] == "URP"
    assert payload["fromPincode"] == 560001
    assert payload["subSupplyType"] == "3"
    assert payload["transMode"] == "2"

    assert getattr(invoice, "transport_distance_km", 250) == 250


def test_bb_000653_cancel_clears_eway_bill_no(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.einvoice_enabled = True
    tenant_a.company.eway_enabled = True
    tenant_a.company.save()
    product = make_product(tenant_a.company, sku="EWC-1", hsn_code="1001")
    add_stock(tenant_a, product, "2")
    customer = make_customer(
        tenant_a.company, gstin="29AABCU9603R1ZJ", state="Karnataka",
        billing_address="Blr 560002",
    )
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "2000", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    invoice.eway_bill_no = "123456789012"
    invoice.eway_status = SalesInvoice.EwayStatus.GENERATED
    invoice.save(update_fields=["eway_bill_no", "eway_status"])
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice.id}/cancel-eway/")
    assert resp.status_code == 200, resp.data
    invoice.refresh_from_db()
    assert invoice.eway_bill_no == ""


@override_settings(DJANGO_ENV="production", GSP_LIVE_ENABLED=True)
def test_bb_000624_live_irp_fail_closed_in_prod(tenant_a):
    tenant_a.company.gsp_provider = "live-gsp"
    with pytest.raises(BusinessRuleError, match="fail-closed|not NIC"):
        get_irp_adapter(tenant_a.company)
    with pytest.raises(BusinessRuleError, match="not NIC-protocol|fail-closed|Disable GSP_LIVE"):
        LiveIrpAdapter(tenant_a.company)
