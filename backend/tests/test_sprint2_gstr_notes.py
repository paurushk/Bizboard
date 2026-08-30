"""Sprint 2: GSTR CDNUR/B2CS, AT/ATADJ, ITC, CMP-08, GSTR-9 Dark, blank POS."""

from decimal import Decimal

import pytest
from django.utils import timezone

from core.services.billing import extract_exclusive_from_inclusive_line, is_intra_state
from purchases.models import PurchaseInvoice
from reporting.gst_returns import build_gstr1, build_gstr3b, build_gstr9, invoice_value_mismatch
from reporting.gstr2b import build_cmp08, claimable_itc_from_2b, match_gstr2b_to_purchases
from reporting.models import Gstr2bIngest
from sales.models import SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, create_draft_purchase, make_customer, make_product, make_supplier

pytestmark = pytest.mark.django_db

PERIOD = timezone.localdate().strftime("%Y-%m")
FY = (
    f"{timezone.localdate().year}-{str(timezone.localdate().year + 1)[-2:]}"
    if timezone.localdate().month >= 4
    else f"{timezone.localdate().year - 1}-{str(timezone.localdate().year)[-2:]}"
)


def _gst_company(tenant):
    tenant.company.gstin = "29ABCDE1234F1ZW"
    tenant.company.state = "Karnataka"
    tenant.company.save()
    return tenant.company


def test_bb_000652_intra_b2c_cn_nets_b2cs_not_cdnur(tenant_a):
    _gst_company(tenant_a)
    product = make_product(tenant_a.company, sku="B2CS-1", hsn_code="1001")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company, state="Karnataka", gstin="")
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "500", "gst_rate": "18"}],
    )
    SalesInvoice.objects.filter(pk=inv["id"]).update(invoice_date=f"{PERIOD}-10")
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    cn = tenant_a.client.post(
        "/api/v1/sales/credit-notes/",
        {
            "customer": customer.id,
            "sales_invoice": inv["id"],
            "note_date": f"{PERIOD}-12",
            "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    assert tenant_a.client.post(f"/api/v1/sales/credit-notes/{cn.data['id']}/complete/").status_code == 200
    payload = build_gstr1(tenant_a.company, PERIOD)
    assert payload["cdnur"] == []
    assert payload["cdnr"] == []
    # CN inherits invoice rates; a full-qty CN nets B2CS to empty/zero.
    assert payload["b2cs"] == [] or any(
        Decimal(str(r["taxable_value"])) < Decimal(str(inv["taxable_total"])) for r in payload["b2cs"]
    )


def test_bb_000652_b2cl_note_goes_cdnur(tenant_a):
    _gst_company(tenant_a)
    product = make_product(tenant_a.company, sku="B2CL-1", hsn_code="1001")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, name="MH URP", state="Maharashtra", gstin="")
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "260000", "gst_rate": "18"}],
    )
    SalesInvoice.objects.filter(pk=inv["id"]).update(invoice_date=f"{PERIOD}-10")
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    cn = tenant_a.client.post(
        "/api/v1/sales/credit-notes/",
        {
            "customer": customer.id,
            "sales_invoice": inv["id"],
            "note_date": f"{PERIOD}-12",
            "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18"}],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    assert tenant_a.client.post(f"/api/v1/sales/credit-notes/{cn.data['id']}/complete/").status_code == 200
    payload = build_gstr1(tenant_a.company, PERIOD)
    assert payload["cdnur"]
    assert all(r["note_kind"] == "CREDIT" for r in payload["cdnur"])


def test_bb_000621_charges_stay_in_b2b_and_atadj_txpd_present(tenant_a):
    _gst_company(tenant_a)
    product = make_product(tenant_a.company, sku="FRT-1", hsn_code="1001")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, gstin="29AABCU9603R1ZJ", state="Karnataka")
    created = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": customer.id,
            "invoice_type": "GST",
            "invoice_date": f"{PERIOD}-08",
            "additional_charges": "40",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "200", "gst_rate": "18"}],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{created.data['id']}/complete/").status_code == 200
    inv = SalesInvoice.objects.get(pk=created.data["id"])
    assert not invoice_value_mismatch(inv)
    rec = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {"customer": customer.id, "amount": "50", "mode": "CASH", "receipt_date": f"{PERIOD}-05"},
        format="json",
    )
    assert rec.status_code == 201, rec.data
    alloc = tenant_a.client.post(
        "/api/v1/payments/allocations/",
        {"receipt": rec.data["id"], "sales_invoice": inv.id, "amount": "50"},
        format="json",
    )
    assert alloc.status_code == 201, alloc.data
    payload = build_gstr1(tenant_a.company, PERIOD)
    assert payload["b2b"]
    assert payload["atadj"]
    assert payload["txpd"][0]["aid_kind"] == "txpd_none"
    assert payload["nil"]["aid_kind"] == "nil_unsplit"
    assert payload["supecom"]["supported"] is False


def test_bb_000614_itc_not_default_claimable(tenant_a):
    _gst_company(tenant_a)
    supplier = make_supplier(tenant_a.company, gstin="29AAAAA0000A1ZY")
    product = make_product(tenant_a.company, sku="ITC-1", hsn_code="1001")
    draft = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    PurchaseInvoice.objects.filter(pk=draft["id"]).update(invoice_date=f"{PERIOD}-04")
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{draft['id']}/complete/").status_code == 200
    inv = PurchaseInvoice.objects.get(pk=draft["id"])
    assert inv.itc_eligibility == PurchaseInvoice.ItcEligibility.UNREVIEWED
    g3 = build_gstr3b(tenant_a.company, PERIOD)
    assert Decimal(str(g3["itc"]["available_from_purchases"]["total_tax"])) == Decimal("0.00")


def test_bb_000637_zip_match_is_read_only(tenant_a):
    row = Gstr2bIngest.objects.create(
        company=tenant_a.company,
        period=PERIOD,
        supplier_gstin="29AAAAA0000A1ZY",
        invoice_number="NO-MATCH",
        taxable_value=Decimal("10"),
        cgst=Decimal("1"),
        sgst=Decimal("1"),
    )
    summary = match_gstr2b_to_purchases(tenant_a.company, PERIOD, persist=False)
    row.refresh_from_db()
    assert summary["persisted"] is False
    assert row.match_status == Gstr2bIngest.MatchStatus.UNMATCHED


def test_bb_000638_blank_pos_is_not_intra():
    assert is_intra_state("Karnataka", "", company_gstin="29ABCDE1234F1ZW") is False


def test_bb_000611_inclusive_extract_includes_cess():
    exclusive, taxable = extract_exclusive_from_inclusive_line(
        quantity=Decimal("1"),
        unit_price_inclusive=Decimal("119"),
        discount_percent=Decimal("0"),
        gst_rate=Decimal("18"),
        cess_rate=Decimal("1"),
    )
    assert taxable == Decimal("100.00")
    assert exclusive == Decimal("100.00")


def test_bb_000623_cmp08_excludes_opening_and_nongst(tenant_a):
    product = make_product(tenant_a.company, sku="CMP-1")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "200", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    SalesInvoice.objects.filter(pk=inv["id"]).update(is_opening_balance=True, invoice_date=f"{PERIOD}-02")
    cmp08 = build_cmp08(tenant_a.company, PERIOD)
    assert Decimal(str(cmp08["outward_taxable"])) == Decimal("0")


def test_bb_000622_dexp_not_in_sez(tenant_a):
    _gst_company(tenant_a)
    product = make_product(tenant_a.company, sku="DEXP-1", hsn_code="1001")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, gstin="27AABCU9603R1ZN", state="Maharashtra")
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "500", "gst_rate": "18"}],
    )
    SalesInvoice.objects.filter(pk=inv["id"]).update(supply_type="DEXP", invoice_date=f"{PERIOD}-03")
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    payload = build_gstr1(tenant_a.company, PERIOD)
    assert payload["sez"] == []
    assert any(r.get("supply_type") == "DEXP" for r in payload["exp"])


def test_bb_000519_gstr9_tables_6_7_dark(tenant_a):
    _gst_company(tenant_a)
    payload = build_gstr9(tenant_a.company, FY)
    assert payload["tables"]["6"]["status"] == "WORKSHEET"
    assert payload["tables"]["6"]["aid_kind"] == "itc_claimable_fy_books"
    assert payload["tables"]["7"]["status"] == "WORKSHEET"
    assert payload["tables"]["7"]["aid_kind"] == "itc_reversal_purchase_cn_fy"
    assert "supecom" in build_gstr1(tenant_a.company, PERIOD)


def test_bb_0001307_supecom_ui_warning():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    page = (root / "web" / "src" / "pages" / "reports" / "GstReturnPage.tsx").read_text(encoding="utf-8")
    gstr9 = (root / "web" / "src" / "pages" / "reports" / "Gstr9ReportPage.tsx").read_text(encoding="utf-8")
    assert "supecomWarning" in page
    assert "gstr9Tables67Worksheet" in gstr9


def test_bb_000614_2b_unreviewed_not_claimable(tenant_a):
    Gstr2bIngest.objects.create(
        company=tenant_a.company,
        period=PERIOD,
        supplier_gstin="29AAAAA0000A1ZY",
        invoice_number="PI-X",
        taxable_value=Decimal("100"),
        cgst=Decimal("9"),
        sgst=Decimal("9"),
        match_status=Gstr2bIngest.MatchStatus.MATCHED,
    )
    itc = claimable_itc_from_2b(tenant_a.company, PERIOD)
    assert itc["cgst"] == Decimal("0")


def test_gstr3b_cess_and_txpd_from_at(tenant_a):
    _gst_company(tenant_a)
    product = make_product(tenant_a.company, sku="CESS-3B", hsn_code="1001")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, gstin="29AABCU9603R1ZJ", state="Karnataka")
    created = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": customer.id,
            "invoice_type": "GST",
            "invoice_date": f"{PERIOD}-08",
            "items": [{
                "product": product.id, "quantity": "1", "unit_price": "100",
                "gst_rate": "18", "cess_rate": "1",
            }],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{created.data['id']}/complete/").status_code == 200
    rec = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {"customer": customer.id, "amount": "40", "mode": "CASH", "receipt_date": f"{PERIOD}-03"},
        format="json",
    )
    assert rec.status_code == 201, rec.data
    g3 = build_gstr3b(tenant_a.company, PERIOD)
    assert Decimal(str(g3["outward_supplies"]["cess"])) == Decimal("1.00")
    assert g3["tax_on_advances"]["txpd"]
    assert g3["tax_on_advances"]["txpd"][0]["aid_kind"] == "txpd_from_at"
    assert g3["tax_on_advances"]["at"]
