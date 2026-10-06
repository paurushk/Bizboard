"""Open GST findings: 16(2), 16(4), e-way Part B, export PIN, 206AB."""

from datetime import date
from decimal import Decimal

import pytest

from accounting.services import apply_specified_person_tds, tds_rate_for_section
from core.exceptions import BusinessRuleError
from purchases.models import PurchaseInvoice
from purchases.services import assert_claimable_itc_allowed
from reporting.gstr2b import claimable_itc_from_2b
from reporting.ims import record_section_16_4_override, section_16_2_checklist
from reporting.models import Gstr2bIngest
from sales.einvoice_eway_actions import extend_eway_validity, update_eway_vehicle
from sales.eway_payload import build_eway_payload_from_invoice
from sales.models import SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, create_draft_purchase, make_customer, make_product, make_supplier

pytestmark = pytest.mark.django_db


def test_bug_gst_003_section_16_2_blocks_claim_before_receipt(tenant_a):
    supplier = make_supplier(tenant_a.company, gstin="29GST030000A1Z5")
    product = make_product(tenant_a.company, sku="GST-003", hsn_code="1001")
    draft = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    invoice = PurchaseInvoice.objects.get(pk=draft["id"])
    invoice.itc_eligibility = PurchaseInvoice.ItcEligibility.CLAIMABLE
    invoice.save(update_fields=["itc_eligibility"])
    with pytest.raises(BusinessRuleError, match="16\\(2\\)"):
        assert_claimable_itc_allowed(invoice)
    blocked = section_16_2_checklist(invoice)
    assert blocked["goods_received"] is False
    assert blocked["passed"] is False

    invoice.itc_eligibility = PurchaseInvoice.ItcEligibility.UNREVIEWED
    invoice.save(update_fields=["itc_eligibility"])
    done = tenant_a.client.post(f"/api/v1/purchases/invoices/{invoice.pk}/complete/")
    assert done.status_code == 200, done.data
    invoice.refresh_from_db()
    invoice.itc_eligibility = PurchaseInvoice.ItcEligibility.CLAIMABLE
    invoice.save(update_fields=["itc_eligibility"])
    assert section_16_2_checklist(invoice)["passed"] is True


def test_bug_gst_002_time_barred_itc_excluded_until_override(tenant_a):
    supplier = make_supplier(tenant_a.company, gstin="29GST020000A1Z8")
    bill = PurchaseInvoice.objects.create(
        company=tenant_a.company,
        supplier=supplier,
        number="PI-16-4",
        supplier_bill_number="SUP-16-4",
        status=PurchaseInvoice.Status.COMPLETED,
        invoice_date=date(2024, 5, 1),
        taxable_total=Decimal("100.00"),
        cgst_total=Decimal("9.00"),
        sgst_total=Decimal("9.00"),
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    row = Gstr2bIngest.objects.create(
        company=tenant_a.company,
        period="2024-05",
        supplier_gstin=supplier.gstin,
        invoice_number="SUP-16-4",
        invoice_date=date(2024, 5, 1),
        taxable_value=Decimal("100.00"),
        cgst=Decimal("9.00"),
        sgst=Decimal("9.00"),
        match_status=Gstr2bIngest.MatchStatus.MATCHED,
        itc_eligibility=Gstr2bIngest.ItcEligibility.CLAIMABLE,
        ims_action=Gstr2bIngest.ImsAction.ACCEPT,
        purchase_invoice=bill,
        section_16_4_deadline=date(2025, 11, 30),
    )
    excluded = claimable_itc_from_2b(tenant_a.company, "2024-05")
    assert excluded["claimable_rows"] == 0
    assert excluded["cgst"] == Decimal("0")
    record_section_16_4_override(row, "Commissioner extension on file")
    restored = claimable_itc_from_2b(tenant_a.company, "2024-05")
    assert restored["claimable_rows"] == 1
    assert restored["cgst"] == Decimal("9.00")


def test_bug_gst_001_part_b_and_validity(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.pincode = "560001"
    tenant_a.company.address = "1 MG Road"
    tenant_a.company.city = "Bengaluru"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    customer = make_customer(
        tenant_a.company, gstin="29AABCU9603R1ZJ", state="Karnataka", billing_address="Blr 560002"
    )
    product = make_product(tenant_a.company, sku="EWB-001", hsn_code="1001")
    add_stock(tenant_a, product, "2")
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    invoice.eway_bill_no = "123456789012"
    invoice.transport_distance_km = 40
    invoice.eway_valid_upto = invoice.completed_at
    invoice.save(update_fields=["eway_bill_no", "transport_distance_km", "eway_valid_upto"])
    update_eway_vehicle(invoice, "KA01AB1234", "1", user=tenant_a.owner)
    invoice.refresh_from_db()
    assert invoice.vehicle_number == "KA01AB1234"
    before = invoice.eway_valid_upto
    extend_eway_validity(invoice, "1", 80, user=tenant_a.owner)
    invoice.refresh_from_db()
    assert invoice.eway_valid_upto > before
    assert invoice.transport_distance_km == 80


def test_bug_gst_006_export_eway_uses_overseas_pin(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.pincode = "560001"
    tenant_a.company.address = "1 MG Road"
    tenant_a.company.city = "Bengaluru"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    customer = make_customer(
        tenant_a.company,
        name="Overseas Buyer",
        state="Karnataka",
        billing_address="10 Downing Street",
        pincode="560001",
    )
    product = make_product(tenant_a.company, sku="EXP-006", hsn_code="1001")
    add_stock(tenant_a, product, "2")
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    customer.pincode = "SW1A 1AA"
    customer.state = ""
    customer.save(update_fields=["pincode", "state"])
    invoice.supply_type = SalesInvoice.SupplyType.EXPWOP
    invoice.sub_supply_type = "3"
    invoice.transport_distance_km = 40
    invoice.trans_mode = "1"
    invoice.save(update_fields=["supply_type", "sub_supply_type", "transport_distance_km", "trans_mode"])
    payload = build_eway_payload_from_invoice(invoice)
    assert payload["toPincode"] == 999999
    assert payload["toStateCode"] == 99
    assert payload["toGstin"] == "URP"


def test_bug_gst_004_specified_person_uses_higher_tds():
    assert tds_rate_for_section("194Q") == Decimal("0.1")
    assert tds_rate_for_section("194Q", specified_person=True) == Decimal("5")
    assert tds_rate_for_section("194C", specified_person=True) == Decimal("5")


def test_bug_gst_004_apply_on_flagged_supplier(tenant_a):
    supplier = make_supplier(tenant_a.company, gstin="29AAAAA0000A1Z5")
    supplier.income_tax_specified_person = True
    supplier.save(update_fields=["income_tax_specified_person"])
    bill = PurchaseInvoice(
        company=tenant_a.company,
        supplier=supplier,
        tds_section="194Q",
        tds_rate=Decimal("0.100"),
        taxable_total=Decimal("10000.00"),
    )
    apply_specified_person_tds(bill)
    assert bill.tds_rate == Decimal("5")
    assert bill.tds_amount == Decimal("500.00")
