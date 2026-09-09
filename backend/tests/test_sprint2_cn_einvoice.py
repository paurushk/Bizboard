"""Sprint 2: CN cap/freeze/return copy + IRN/e-way honesty."""

from decimal import Decimal
import pytest
from django.test import override_settings

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
    done = tenant_a.client.post(
        f"/api/v1/sales/credit-notes/{cn.data['id']}/complete/",
        {"confirm_paid_invoice": True},
        format="json",
    )
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

    # BB-000663 / BILL-04: `taxable_total` is stored net of *line* discounts only;
    # the header-level AFTER_TAX `invoice_discount` is a separate subtraction, not
    # folded into `taxable_total`. The auto-return credit note copies the invoice
    # discount and runs the same billing math, so its header totals must foot the
    # *same* way the source invoice's do:
    #   taxable + cgst + sgst + igst + cess + charges − invoice_discount ± round_off == grand_total
    # (charges are non-taxable on this NON_GST path, so they sit outside taxable_total.)
    invoice = SalesInvoice.objects.get(pk=created.data["id"])
    for doc in (invoice, note):
        footed = (
            doc.taxable_total
            + doc.cgst_total
            + doc.sgst_total
            + doc.igst_total
            + doc.cess_total
            + Decimal(str(getattr(doc, "additional_charges", 0) or 0))
            - Decimal(str(doc.invoice_discount or 0))
            + doc.round_off
        )
        assert footed == doc.grand_total, (
            f"{doc.__class__.__name__} header totals do not foot: "
            f"{footed} != {doc.grand_total}"
        )


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
    assert (
        tenant_a.client.post(
            f"/api/v1/sales/credit-notes/{cn.data['id']}/complete/",
            {"confirm_price_override": True},
            format="json",
        ).status_code
        == 200
    )
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
    # ACCT-02: creating the primary CompanyGstin now mirrors it into the
    # Company.gstin scalar so direct scalar readers (billing / doc numbers /
    # GSTR) stay consistent with the multi-GSTIN model.
    invoice.company.refresh_from_db()
    assert invoice.company.gstin == "29ABCDE1234F1ZW"


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


def test_b2_015_eway_cancel_blocked_after_24h_of_generation(tenant_a):
    from datetime import timedelta

    from django.utils import timezone

    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.einvoice_enabled = True
    tenant_a.company.eway_enabled = True
    tenant_a.company.save()
    product = make_product(tenant_a.company, sku="EWC-2", hsn_code="1001")
    add_stock(tenant_a, product, "2")
    customer = make_customer(
        tenant_a.company, gstin="29AABCU9603R1ZJ", state="Karnataka",
        billing_address="Blr 560002",
    )
    inv = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "2000", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    invoice.eway_bill_no = "123456789099"
    invoice.eway_status = SalesInvoice.EwayStatus.GENERATED
    invoice.eway_generated_at = timezone.now() - timedelta(hours=25)
    invoice.save(update_fields=["eway_bill_no", "eway_status", "eway_generated_at"])

    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice.id}/cancel-eway/")
    assert resp.status_code == 400, resp.data
    assert "24 hours" in str(resp.data)
    invoice.refresh_from_db()
    assert invoice.eway_bill_no == "123456789099"  # not cancelled

    # Still within the window -> cancel succeeds.
    invoice.eway_generated_at = timezone.now() - timedelta(hours=23)
    invoice.save(update_fields=["eway_generated_at"])
    resp2 = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice.id}/cancel-eway/")
    assert resp2.status_code == 200, resp2.data
    invoice.refresh_from_db()
    assert invoice.eway_bill_no == ""


@override_settings(DJANGO_ENV="production", GSP_LIVE_ENABLED=True)
def test_bb_000624_live_irp_fail_closed_in_prod(tenant_a):
    tenant_a.company.gsp_provider = "live-gsp"
    with pytest.raises(BusinessRuleError, match="fail-closed|not NIC"):
        get_irp_adapter(tenant_a.company)
    with pytest.raises(BusinessRuleError, match="not NIC-protocol|fail-closed|Disable GSP_LIVE"):
        LiveIrpAdapter(tenant_a.company)


@override_settings(DJANGO_ENV="production", GSP_LIVE_ENABLED=True, GSP_CERTIFIED=True)
def test_b7_004_live_irp_refuses_custom_provider_even_when_certified(tenant_a):
    """B7-004: 'custom' provider's payload wrapper is an HMAC placeholder, not
    real NIC SEK/AES encryption -- must refuse even when GSP_CERTIFIED=1,
    since certification never actually covered the 'custom' wrapper.
    GSP_PROVIDER defaults to "custom" (settings.py) unless the env var is set,
    and resolve_gsp_provider() checks the *setting* before company.gsp_provider
    -- override the setting itself to exercise the "genuinely certified" path."""
    tenant_a.company.gsp_provider = "custom"
    with pytest.raises(BusinessRuleError, match="custom.*HMAC placeholder|not real NIC SEK"):
        LiveIrpAdapter(tenant_a.company)

    # A genuinely certified provider still constructs fine under the same flags.
    with override_settings(GSP_PROVIDER="cleartax"):
        LiveIrpAdapter(tenant_a.company)


def test_cr_013_einvoice_cancel_retains_statutory_irn(tenant_a):
    """CR-013: Statutory record retention requires IRN, AckNo, AckDt to be preserved on cancel."""
    from django.utils import timezone
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.einvoice_enabled = True
    tenant_a.company.save()
    product = make_product(tenant_a.company, sku="EINV-1", hsn_code="1001")
    add_stock(tenant_a, product, "5")
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
    invoice.irn = "a" * 64
    invoice.ack_no = "123456789012"
    invoice.ack_date = timezone.now()
    invoice.einvoice_status = SalesInvoice.EInvoiceStatus.GENERATED
    invoice.einvoice_qr = "QR_DATA_HERE"
    invoice.save(update_fields=["irn", "ack_no", "ack_date", "einvoice_status", "einvoice_qr"])

    # Cancel the e-invoice
    resp = tenant_a.client.post(
        f"/api/v1/sales/invoices/{invoice.id}/cancel-einvoice/",
        {"cnl_rsn": "1", "cnl_rem": "Duplicate invoice"},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    invoice.refresh_from_db()
    assert invoice.einvoice_status == SalesInvoice.EInvoiceStatus.CANCELLED
    assert invoice.irn == "a" * 64, "IRN must be retained for 6-year statutory audit trail"
    assert invoice.ack_no == "123456789012"
    assert invoice.ack_date is not None
    assert invoice.einvoice_qr == ""

    # Re-submitting cancelled invoice must be rejected
    resp_re = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice.id}/submit-einvoice/")
    assert resp_re.status_code in (400, 409)

