"""Phase 2 GST returns readiness — rate-wise GSTR, health, snapshots, RCM, inclusive."""

from decimal import Decimal

import pytest

from core.services.billing import extract_exclusive_from_inclusive_line, place_of_supply_known, q2
from core.services.uqc import normalize_uqc, resolve_uqc_code
from reporting.gst_returns import (
    build_gstr1,
    content_hash,
    invoice_value_mismatch,
    persist_snapshot,
)
from reporting.gst_health import build_gst_health
from reporting.models import GstReturnSnapshot
from sales.einvoice_payload import EinvoiceValidationError, build_einvoice_payload
from sales.models import SalesInvoice, SalesItem
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db

PERIOD = "2026-07"


def _complete(tenant, customer, product, *, unit_price="1000", gst_rate="18", invoice_date=PERIOD + "-15", extra_items=None):
    items = [{"product": product.id, "quantity": "1", "unit_price": unit_price, "gst_rate": gst_rate}]
    if extra_items:
        items.extend(extra_items)
    payload = {
        "customer": customer.id,
        "invoice_type": "GST",
        "invoice_date": invoice_date,
        "items": items,
    }
    resp = tenant.client.post("/api/v1/sales/invoices/", payload, format="json")
    assert resp.status_code == 201, resp.data
    done = tenant.client.post(f"/api/v1/sales/invoices/{resp.data['id']}/complete/")
    assert done.status_code == 200, done.data
    return done.data


def test_uqc_normalize_and_resolve():
    assert normalize_uqc("pcs") == "PCS"
    assert normalize_uqc("kilogram") == "KGS"
    assert resolve_uqc_code(unit_name="BOX") == "BOX"


def test_inclusive_extract_matches_discounted_gross():
    exclusive, taxable = extract_exclusive_from_inclusive_line(
        quantity=Decimal("2"),
        unit_price_inclusive=Decimal("118"),
        discount_percent=Decimal("0"),
        gst_rate=Decimal("18"),
    )
    assert taxable == Decimal("200.00")
    assert exclusive == Decimal("100.00")


def test_gstr1_rate_wise_multi_rate(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    p5 = make_product(tenant_a.company, sku="P5", gst_rate="5", hsn_code="8501")
    p28 = make_product(tenant_a.company, sku="P28", gst_rate="28", hsn_code="8502")
    add_stock(tenant_a, p5, "10")
    add_stock(tenant_a, p28, "10")
    cust = make_customer(tenant_a.company, name="Reg Co", state="Karnataka", gstin="29AABCU9603R1ZJ")
    _complete(
        tenant_a,
        cust,
        p5,
        unit_price="100",
        gst_rate="5",
        extra_items=[{"product": p28.id, "quantity": "1", "unit_price": "200", "gst_rate": "28"}],
    )
    payload = build_gstr1(tenant_a.company, PERIOD)
    rates = sorted((row["rate"] for row in payload["b2b"]), key=lambda r: Decimal(r))
    assert rates == ["5.00", "28.00"]
    assert payload["hsn"]
    assert any(row["hsn"] == "8501" for row in payload["hsn"])


def test_gstr1_reconciliation_invariant(tenant_a):
    """GSTR net taxable matches sales register GST rows, excluding invoice_value mismatches."""
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    product = make_product(tenant_a.company, sku="INV", hsn_code="3004")
    add_stock(tenant_a, product, "50")
    b2b = make_customer(tenant_a.company, name="B2B", state="Karnataka", gstin="29AABCU9603R1ZJ")
    b2c = make_customer(tenant_a.company, name="B2C", state="Karnataka")
    _complete(tenant_a, b2b, product, unit_price="1000")
    _complete(tenant_a, b2c, product, unit_price="500", invoice_date=PERIOD + "-10")

    payload = build_gstr1(tenant_a.company, PERIOD)
    section = (
        sum(Decimal(r["taxable_value"]) for r in payload["b2b"])
        + sum(Decimal(r["taxable_value"]) for r in payload["b2cl"])
        + sum(Decimal(r["taxable_value"]) for r in payload["b2cs"])
        - sum(Decimal(r["taxable_value"]) for r in payload["cdnr"] if r["note_kind"] == "CREDIT")
        - sum(Decimal(r["taxable_value"]) for r in payload["cdnur"] if r["note_kind"] == "CREDIT")
        + sum(Decimal(r["taxable_value"]) for r in payload["cdnr"] if r["note_kind"] == "DEBIT")
        + sum(Decimal(r["taxable_value"]) for r in payload["cdnur"] if r["note_kind"] == "DEBIT")
    )
    assert q2(section) == Decimal(payload["totals"]["section_net_taxable"])
    # Without mismatches, register GST invoices (+ notes signed) match outward liability.
    assert q2(section) == Decimal(payload["totals"]["outward_taxable"])

    register = tenant_a.client.get(
        "/api/v1/reports/sales-register/",
        {"date_from": "2026-07-01", "date_to": "2026-07-31"},
    )
    assert register.status_code == 200
    register_taxable = Decimal("0")
    for row in register.data["rows"]:
        if row.get("status") == "CANCELLED":
            continue
        itype = row.get("invoice_type")
        if itype == "NON_GST":
            continue
        taxable = Decimal(str(row["taxable"]))
        if itype == "CREDIT_NOTE":
            register_taxable -= taxable
        elif itype == "DEBIT_NOTE":
            register_taxable += taxable
        else:
            register_taxable += taxable
    assert q2(register_taxable) == Decimal(payload["totals"]["outward_taxable"])


def test_invoice_value_mismatch_excluded(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    product = make_product(tenant_a.company, sku="CHG", hsn_code="3004")
    add_stock(tenant_a, product, "10")
    cust = make_customer(tenant_a.company, name="B2B", state="Karnataka", gstin="29AABCU9603R1ZJ")
    draft = create_draft_invoice(
        tenant_a,
        cust,
        [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18"}],
    )
    inv = SalesInvoice.objects.get(pk=draft["id"])
    resp = tenant_a.client.patch(
        f"/api/v1/sales/invoices/{inv.id}/",
        {
            "invoice_date": PERIOD + "-15",
            "additional_charges": "50",
            "items": [
                {"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18"}
            ],
        },
        format="json",
    )
    assert resp.status_code == 200, resp.data
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv.id}/complete/")
    assert done.status_code == 200, done.data
    inv.refresh_from_db()
    assert Decimal(str(inv.additional_charges)) == Decimal("50")
    assert not invoice_value_mismatch(inv)
    payload = build_gstr1(tenant_a.company, PERIOD)
    assert payload["b2b"]
    assert all(i.get("code") != "INVOICE_VALUE_MISMATCH" for i in payload.get("issues", []))


def test_snapshot_hash_stable(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    product = make_product(tenant_a.company, sku="SNAP", hsn_code="3004")
    add_stock(tenant_a, product, "5")
    cust = make_customer(tenant_a.company, name="B2B", state="Karnataka", gstin="29AABCU9603R1ZJ")
    _complete(tenant_a, cust, product)
    p1 = build_gstr1(tenant_a.company, PERIOD)
    p2 = build_gstr1(tenant_a.company, PERIOD)
    assert content_hash(p1) == content_hash(p2)
    snap = persist_snapshot(tenant_a.company, "GSTR-1", PERIOD, p1, user=tenant_a.owner)  # noqa: F841
    assert snap.content_hash == content_hash(p1)
    assert GstReturnSnapshot.objects.filter(company=tenant_a.company, period=PERIOD).exists()


def test_identity_amend_and_health(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.aato_turnover = Decimal("60000000")
    tenant_a.company.einvoice_enabled = False
    tenant_a.company.save()
    product = make_product(tenant_a.company, sku="ID", hsn_code="3004")
    add_stock(tenant_a, product, "5")
    cust = make_customer(tenant_a.company, name="B2B", state="Karnataka", gstin="29AABCU9603R1ZJ")
    inv = _complete(tenant_a, cust, product)
    # persist snapshot then amend → dirty
    payload = build_gstr1(tenant_a.company, PERIOD)
    persist_snapshot(tenant_a.company, "GSTR-1", PERIOD, payload, user=tenant_a.owner)
    resp = tenant_a.client.post(
        f"/api/v1/sales/invoices/{inv['id']}/amend-filing-identity/",
        {"filing_party_gstin": "29AAACW3775F1Z2", "filing_place_of_supply": "29", "reason": "wrong GSTIN"},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    assert resp.data["filing_party_gstin"] == "29AAACW3775F1Z2"
    health = build_gst_health(tenant_a.company, PERIOD)
    codes = {a["code"] for a in health["alerts"]}
    assert "PERIOD_CHANGED_AFTER_SNAPSHOT" in codes
    assert "EINVOICE_MANDATORY_NOT_ENABLED" in codes


def test_cn_line_snapshots_hsn_uqc(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    product = make_product(tenant_a.company, sku="CN", hsn_code="3004")
    add_stock(tenant_a, product, "5")
    cust = make_customer(tenant_a.company, name="B2B", state="Karnataka", gstin="29AABCU9603R1ZJ")
    inv = _complete(tenant_a, cust, product, unit_price="1000")
    item = SalesItem.objects.get(invoice_id=inv["id"])
    assert item.hsn_code == "3004"
    assert item.uqc_code
    # Product HSN diverges after invoice — CN must keep source line snapshot.
    product.hsn_code = "9999"
    product.save(update_fields=["hsn_code"])
    cn = tenant_a.client.post(
        "/api/v1/sales/credit-notes/",
        {
            "customer": cust.id,
            "sales_invoice": inv["id"],
            "note_date": PERIOD + "-20",
            "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "200", "gst_rate": "18", "source_item": item.id}],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    assert cn.data["items"][0]["hsn_code"] == "3004"
    assert cn.data["items"][0]["uqc_code"]


def test_submit_einvoice_sandbox(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "29-Karnataka"
    tenant_a.company.address = "1 Main St"
    tenant_a.company.pincode = "560001"
    tenant_a.company.einvoice_enabled = True
    tenant_a.company.save()
    product = make_product(tenant_a.company, sku="EI", hsn_code="3004")
    add_stock(tenant_a, product, "5")
    cust = make_customer(
        tenant_a.company,
        name="B2B",
        state="29-Karnataka",
        gstin="29AABCU9603R1ZJ",
    )
    # billing address + 6-digit PIN in text (Party has no pincode column)
    cust.billing_address = "Buyer Street, 560002"
    cust.save(update_fields=["billing_address"])
    inv = _complete(tenant_a, cust, product)
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/submit-einvoice/")
    assert resp.status_code == 200, resp.data
    assert resp.data["einvoice_status"] == "GENERATED"
    assert resp.data["irn"]


def test_rcm_purchase_memo(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    from tests.conftest import make_supplier

    supplier = make_supplier(tenant_a.company, name="URP", state="Karnataka", gstin="")
    product = make_product(tenant_a.company, sku="RCM", hsn_code="9983")
    resp = tenant_a.client.post(
        "/api/v1/purchases/invoices/",
        {
            "supplier": supplier.id,
            "purchase_type": "GST",
            "invoice_date": PERIOD + "-12",
            "is_reverse_charge": True,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18"}],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    # Draft payable must already apply RCM (not only on Complete).
    assert Decimal(resp.data["rcm_taxable"]) == Decimal("1000.00")
    assert Decimal(resp.data["cgst_total"]) == Decimal("0.00")
    assert Decimal(resp.data["grand_total"]) in (Decimal("1000.00"), Decimal("1000"))
    line = resp.data["items"][0]
    assert Decimal(str(line["cgst"])) == Decimal("0.00")
    assert Decimal(str(line["sgst"])) == Decimal("0.00")
    done = tenant_a.client.post(f"/api/v1/purchases/invoices/{resp.data['id']}/complete/")
    assert done.status_code == 200, done.data
    assert Decimal(done.data["rcm_taxable"]) == Decimal("1000.00")
    assert Decimal(done.data["cgst_total"]) == Decimal("0.00")
    assert Decimal(done.data["grand_total"]) == Decimal("1000.00") or Decimal(done.data["grand_total"]) == Decimal("1000")


def test_inclusive_resave_idempotent(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    product = make_product(tenant_a.company, sku="INC", hsn_code="3004")
    add_stock(tenant_a, product, "5")
    cust = make_customer(tenant_a.company, name="B2B", state="Karnataka", gstin="29AABCU9603R1ZJ")
    payload = {
        "customer": cust.id,
        "invoice_type": "GST",
        "invoice_date": PERIOD + "-15",
        "price_mode": "INCLUSIVE",
        "items": [{
            "product": product.id,
            "quantity": "1",
            "unit_price": "118",
            "unit_price_inclusive": "118",
            "gst_rate": "18",
        }],
    }
    created = tenant_a.client.post("/api/v1/sales/invoices/", payload, format="json")
    assert created.status_code == 201, created.data
    inv_id = created.data["id"]
    assert Decimal(created.data["taxable_total"]) == Decimal("100.00")
    item = SalesItem.objects.get(invoice_id=inv_id)
    exclusive_once = item.unit_price
    assert exclusive_once == Decimal("100.00")
    # Re-save with exclusive unit_price + same inclusive — must not double-extract.
    again = tenant_a.client.patch(
        f"/api/v1/sales/invoices/{inv_id}/",
        {
            "price_mode": "INCLUSIVE",
            "items": [{
                "product": product.id,
                "quantity": "1",
                "unit_price": str(exclusive_once),
                "unit_price_inclusive": "118",
                "gst_rate": "18",
            }],
        },
        format="json",
    )
    assert again.status_code == 200, again.data
    item = SalesItem.objects.get(invoice_id=inv_id)
    assert item.unit_price == Decimal("100.00")
    assert Decimal(again.data["taxable_total"]) == Decimal("100.00")


def test_party_gstin_missing_b2b_alert(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    product = make_product(tenant_a.company, sku="BIG", hsn_code="3004")
    add_stock(tenant_a, product, "5")
    b2c = make_customer(tenant_a.company, name="Cash", state="Karnataka", gstin="")
    _complete(tenant_a, b2c, product, unit_price="50000")
    health = build_gst_health(tenant_a.company, PERIOD)
    codes = {a["code"] for a in health["alerts"]}
    assert "PARTY_GSTIN_MISSING_B2B" in codes


def test_gsp_credentials_write_only(tenant_a):
    resp = tenant_a.client.patch(
        "/api/v1/company/",
        {
            "gsp_provider": "sandbox",
            "gsp_credentials": {"client_id": "abc", "client_secret": "secret"},
        },
        format="json",
    )
    assert resp.status_code == 200, resp.data
    assert "gsp_credentials" not in resp.data
    assert "client_secret" not in str(resp.data)
    tenant_a.company.refresh_from_db()
    assert not (tenant_a.company.gsp_credentials_encrypted or "")
    assert (tenant_a.company.gsp_provider or "") == ""


def test_gstin_verify_customer(tenant_a):
    cust = make_customer(tenant_a.company, name="V", state="Karnataka", gstin="29AABCU9603R1ZJ")
    resp = tenant_a.client.post(f"/api/v1/customers/{cust.id}/verify-gstin/")
    assert resp.status_code == 200, resp.data
    assert resp.data["gstin_verification_status"] == "UNVERIFIED"
    # BB-000285/225: Null provider must never set VALID or gstin_verified_at.
    assert resp.data["gstin_verification_status"] != "VALID"
    assert resp.data.get("gstin_verified_at") in (None, "")
    cust.refresh_from_db()
    assert cust.gstin_verified_at is None
    assert cust.gstin_verification_status == "UNVERIFIED"


def test_composition_blocked_from_gstr1(tenant_a):
    from accounts.models import Company

    tenant_a.company.registration_type = Company.RegistrationType.COMPOSITION
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.save()
    resp = tenant_a.client.get("/api/v1/reports/gstr1/", {"period": PERIOD})
    assert resp.status_code == 400


def test_gstr9_and_ca_pack(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    product = make_product(tenant_a.company, sku="Y9", hsn_code="3004")
    add_stock(tenant_a, product, "5")
    cust = make_customer(tenant_a.company, name="B2B", state="Karnataka", gstin="29AABCU9603R1ZJ")
    _complete(tenant_a, cust, product)
    resp = tenant_a.client.get("/api/v1/reports/gstr9/", {"fy": "2026-27"})
    assert resp.status_code == 200, resp.data
    assert resp.data.get("aid_kind") in ("outward_fy_aid", "gstr9_worksheet_mvp")
    assert "inward_taxable" in resp.data["annual"]
    monthly_sum = sum(Decimal(str(m["outward_taxable"])) for m in resp.data["monthly"])
    assert q2(monthly_sum) == Decimal(str(resp.data["annual"]["outward_taxable"]))
    pack = tenant_a.client.get("/api/v1/reports/gst-ca-pack/", {"period": PERIOD})
    assert pack.status_code == 200
    assert pack["Content-Type"] == "application/zip"


def test_gstr1_golden_multi_rate_fixture(tenant_a):
    import json
    from pathlib import Path

    golden = json.loads(
        (Path(__file__).parent / "fixtures" / "gst" / "gstr1_multi_rate_month.json").read_text()
    )
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    products = {}
    for line in golden["lines"]:
        p = make_product(
            tenant_a.company,
            sku=line["sku"],
            gst_rate=line["gst_rate"],
            hsn_code=line["hsn"],
        )
        add_stock(tenant_a, p, "10")
        products[line["sku"]] = p
    cust = make_customer(tenant_a.company, name="Reg Co", state="Karnataka", gstin="29AABCU9603R1ZJ")
    first, *rest = golden["lines"]
    _complete(
        tenant_a,
        cust,
        products[first["sku"]],
        unit_price=first["unit_price"],
        gst_rate=first["gst_rate"],
        extra_items=[
            {
                "product": products[line["sku"]].id,
                "quantity": line["quantity"],
                "unit_price": line["unit_price"],
                "gst_rate": line["gst_rate"],
            }
            for line in rest
        ],
    )
    payload = build_gstr1(tenant_a.company, golden["period"])
    rates = sorted((row["rate"] for row in payload["b2b"]), key=lambda r: Decimal(r))
    assert rates == golden["expected"]["b2b_rates"]
    assert Decimal(payload["totals"]["outward_taxable"]) == Decimal(golden["expected"]["outward_taxable"])
    hsn_set = {row["hsn"] for row in payload["hsn"]}
    assert set(golden["expected"]["hsn_codes"]).issubset(hsn_set)


def test_inclusive_discount_persists_and_notes_patch(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    product = make_product(tenant_a.company, sku="INCD", hsn_code="8501")
    add_stock(tenant_a, product, "5")
    cust = make_customer(tenant_a.company, name="B2B", state="Karnataka", gstin="29AABCU9603R1ZJ")
    created = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust.id,
            "invoice_type": "GST",
            "invoice_date": PERIOD + "-15",
            "price_mode": "INCLUSIVE",
            "items": [{
                "product": product.id,
                "quantity": "1",
                "unit_price": "118",
                "unit_price_inclusive": "118",
                "discount_percent": "10",
                "gst_rate": "18",
            }],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    assert Decimal(created.data["taxable_total"]) == Decimal("90.00")
    assert Decimal(str(created.data["items"][0]["discount_percent"])) == Decimal("10.00")
    inv_id = created.data["id"]
    # Items-less PATCH must not double-extract.
    notes = tenant_a.client.patch(
        f"/api/v1/sales/invoices/{inv_id}/",
        {"notes": "hello"},
        format="json",
    )
    assert notes.status_code == 200, notes.data
    assert Decimal(notes.data["taxable_total"]) == Decimal("90.00")
    item = SalesItem.objects.get(invoice_id=inv_id)
    assert item.unit_price == Decimal("90.00")
    assert Decimal(str(item.discount_percent)) == Decimal("10.00")
    assert Decimal(str(item.unit_price_inclusive)) == Decimal("118.00")


def test_source_item_cross_tenant_rejected(tenant_a, tenant_b):
    product_a = make_product(tenant_a.company, sku="SA", hsn_code="3004")
    add_stock(tenant_a, product_a, "5")
    cust_a = make_customer(tenant_a.company, name="A", state="Karnataka", gstin="29AABCU9603R1ZJ")
    inv_a = _complete(tenant_a, cust_a, product_a)
    item_a = SalesItem.objects.get(invoice_id=inv_a["id"])

    product_b = make_product(tenant_b.company, sku="SB", hsn_code="8888")
    add_stock(tenant_b, product_b, "5")
    cust_b = make_customer(tenant_b.company, name="B", state="Karnataka", gstin="29AAACW3775F1Z2")
    inv_b = _complete(tenant_b, cust_b, product_b)

    cn = tenant_b.client.post(
        "/api/v1/sales/credit-notes/",
        {
            "customer": cust_b.id,
            "sales_invoice": inv_b["id"],
            "note_date": PERIOD + "-20",
            "reason": "CORRECTION_OF_INVOICE",
            "items": [{
                "product": product_b.id,
                "quantity": "1",
                "unit_price": "100",
                "gst_rate": "18",
                "source_item": item_a.id,
            }],
        },
        format="json",
    )
    assert cn.status_code == 400, cn.data


def test_purchase_debit_note_source_item_cross_tenant_rejected(tenant_a, tenant_b):
    from purchases.models import PurchaseItem
    from tests.conftest import create_draft_purchase, make_supplier

    product_a = make_product(tenant_a.company, sku="PA")
    supplier_a = make_supplier(tenant_a.company, name="SupA")
    pur_a = create_draft_purchase(tenant_a, supplier_a, [
        {"product": product_a.id, "quantity": "2", "unit_price": "50"},
    ])
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur_a['id']}/complete/").status_code == 200
    item_a = PurchaseItem.objects.get(invoice_id=pur_a["id"])

    product_b = make_product(tenant_b.company, sku="PB")
    supplier_b = make_supplier(tenant_b.company, name="SupB")
    pur_b = create_draft_purchase(tenant_b, supplier_b, [
        {"product": product_b.id, "quantity": "2", "unit_price": "50"},
    ])
    assert tenant_b.client.post(f"/api/v1/purchases/invoices/{pur_b['id']}/complete/").status_code == 200

    dn = tenant_b.client.post(
        "/api/v1/purchases/debit-notes/",
        {
            "supplier": supplier_b.id,
            "purchase_invoice": pur_b["id"],
            "note_date": PERIOD + "-20",
            "reason": "CORRECTION_OF_INVOICE",
            "items": [{
                "product": product_b.id,
                "quantity": "1",
                "unit_price": "50",
                "gst_rate": "18",
                "source_item": item_a.id,
            }],
        },
        format="json",
    )
    assert dn.status_code == 400, dn.data


def test_gstr3b_outward_includes_charges_invoice(tenant_a):
    from reporting.gst_returns import build_gstr3b

    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    product = make_product(tenant_a.company, sku="CHG3", hsn_code="3004")
    add_stock(tenant_a, product, "5")
    cust = make_customer(tenant_a.company, name="B2B", state="Karnataka", gstin="29AABCU9603R1ZJ")
    created = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust.id,
            "invoice_type": "GST",
            "invoice_date": PERIOD + "-15",
            "additional_charges": "50",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18"}],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{created.data['id']}/complete/")
    assert done.status_code == 200, done.data
    assert not invoice_value_mismatch(SalesInvoice.objects.get(pk=created.data["id"]))
    from reporting.gst_returns import build_gstr1

    g1 = build_gstr1(tenant_a.company, PERIOD)
    g3 = build_gstr3b(tenant_a.company, PERIOD, gstr1=g1)
    outward = g3["outward_supplies"]
    # BB-000621: freight/charges invoices stay in outward sections when totals reconcile.
    assert Decimal(str(outward["taxable_value"])) == Decimal("1000.00")
    assert all(i.get("code") != "INVOICE_VALUE_MISMATCH" for i in g1.get("issues", []))


def test_gsp_credentials_merge(tenant_a):
    again = tenant_a.client.patch(
        "/api/v1/company/",
        {"gsp_credentials": {"client_id": "xyz", "client_secret": "secret"}},
        format="json",
    )
    assert again.status_code == 200, again.data
    tenant_a.company.refresh_from_db()
    assert not (tenant_a.company.gsp_credentials_encrypted or "")


def test_place_of_supply_known_requires_mappable_code():
    """BB-000365: place_of_supply_known must require an actually mappable
    2-digit GST state code — free text that doesn't map to a known state/UT
    is not 'known' just because it's non-empty."""
    assert place_of_supply_known(party_state="Karnataka") is True
    assert place_of_supply_known(party_gstin="29AABCU9603R1ZJ") is True
    assert place_of_supply_known(party_state="Nowhereland") is False
    assert place_of_supply_known(party_state="", party_gstin="") is False


def test_pos_complete_rejects_unmapped_free_text_state(tenant_a):
    """BB-000333: completing a tax-enabled invoice for a customer whose state
    cannot be mapped to a GST state code (and has no GSTIN) must hard-fail
    instead of silently persisting unmapped free text as place of supply."""
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    product = make_product(tenant_a.company, sku="POS-BAD", hsn_code="3004")
    add_stock(tenant_a, product, "5")
    cust = make_customer(tenant_a.company, name="Bad State", state="Nowhereland", gstin="")
    draft = create_draft_invoice(
        tenant_a, cust, [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert resp.status_code == 400
    assert "place-of-supply" in str(resp.data).lower() or "place of supply" in str(resp.data).lower()


def test_pos_complete_persists_two_digit_code(tenant_a):
    """BB-000333: completing an invoice always persists a mappable 2-digit
    filing_place_of_supply, never a raw state name."""
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    product = make_product(tenant_a.company, sku="POS-OK", hsn_code="3004")
    add_stock(tenant_a, product, "5")
    cust = make_customer(tenant_a.company, name="Good State", state="Karnataka", gstin="")
    inv = _complete(tenant_a, cust, product, unit_price="100")
    assert inv["filing_place_of_supply"] == "29"


def test_amend_filing_identity_blocks_intra_inter_flip(tenant_a):
    """BB-000334: amending filing GSTIN/POS to flip intra-state <-> inter-state
    classification is blocked — it would change the tax owed without a
    recompute."""
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    product = make_product(tenant_a.company, sku="FLIP", hsn_code="3004")
    add_stock(tenant_a, product, "5")
    # Unregistered (B2C) buyer: without a party GSTIN, the filing POS override
    # is what actually drives intra/inter classification.
    cust = make_customer(tenant_a.company, name="B2C", state="Karnataka", gstin="")
    inv = _complete(tenant_a, cust, product)
    resp = tenant_a.client.post(
        f"/api/v1/sales/invoices/{inv['id']}/amend-filing-identity/",
        {"filing_place_of_supply": "27", "reason": "test flip"},
        format="json",
    )
    assert resp.status_code == 400
    assert "flip" in str(resp.data).lower() or "inter-state" in str(resp.data).lower()


def test_gstr1_b2cl_classifies_by_filing_pos_override(tenant_a):
    """BB-000365: B2CL/B2CS classification must use the resolved filing
    place-of-supply (which may be explicitly overridden for ship-to purposes),
    not blindly the customer master's billing state."""
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    product = make_product(tenant_a.company, sku="POSOVR", hsn_code="3004")
    add_stock(tenant_a, product, "5")
    # Same-state (intra) customer on paper, but shipped inter-state — filing POS
    # explicitly overridden to Delhi at creation time.
    cust = make_customer(tenant_a.company, name="ShipTo", state="Karnataka", gstin="")
    resp = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust.id,
            "invoice_type": "GST",
            "invoice_date": PERIOD + "-15",
            "filing_place_of_supply": "07",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "150000", "gst_rate": "18"}],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{resp.data['id']}/complete/")
    assert done.status_code == 200, done.data

    payload = build_gstr1(tenant_a.company, PERIOD)
    assert len(payload["b2cl"]) == 1
    assert payload["b2cl"][0]["place_of_supply"] == "07"
    assert not payload["b2cs"]


def test_einvoice_payload_requires_buyer_gstin(tenant_a):
    """BB-000324: e-Invoice B2B payload must never be built without a buyer
    GSTIN — unregistered/B2C buyers are not supported for e-Invoice."""
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.address = "1 Main St"
    tenant_a.company.save()
    product = make_product(tenant_a.company, sku="EINV-NOGSTIN", hsn_code="3004")
    add_stock(tenant_a, product, "5")
    cust = make_customer(tenant_a.company, name="B2C", state="Karnataka", gstin="")
    inv = _complete(tenant_a, cust, product)
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    with pytest.raises(EinvoiceValidationError) as exc:
        build_einvoice_payload(invoice)
    assert any("gstin" in msg.lower() for msg in exc.value.errors)


def test_completed_rcm_toggle_off_clears_rcm_fields(tenant_a):
    """BB-000362: toggling is_reverse_charge back to False after a completed
    RCM purchase must clear the stale rcm_* fields, not leave them dangling."""
    from tests.conftest import make_supplier

    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    supplier = make_supplier(tenant_a.company, name="S-RCM-OFF", state="Karnataka", gstin="29AABCU9603R1ZJ")
    product = make_product(tenant_a.company, sku="RCMOFF", hsn_code="9983")
    created = tenant_a.client.post(
        "/api/v1/purchases/invoices/",
        {
            "supplier": supplier.id,
            "purchase_type": "GST",
            "invoice_date": PERIOD + "-12",
            "is_reverse_charge": True,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18"}],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    done = tenant_a.client.post(f"/api/v1/purchases/invoices/{created.data['id']}/complete/")
    assert done.status_code == 200, done.data
    assert Decimal(done.data["rcm_taxable"]) == Decimal("1000.00")

    toggled = tenant_a.client.patch(
        f"/api/v1/purchases/invoices/{created.data['id']}/",
        {"is_reverse_charge": False, "confirm_amend": True},
        format="json",
    )
    assert toggled.status_code == 200, toggled.data
    assert Decimal(toggled.data["rcm_taxable"]) == Decimal("0.00")
    assert Decimal(toggled.data["rcm_cgst"]) == Decimal("0.00")
    assert Decimal(toggled.data["rcm_sgst"]) == Decimal("0.00")
    assert Decimal(toggled.data["rcm_igst"]) == Decimal("0.00")
    assert Decimal(toggled.data["cgst_total"]) + Decimal(toggled.data["sgst_total"]) > 0


def test_completed_rcm_toggle_recomputation(tenant_a):
    from tests.conftest import make_supplier

    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    supplier = make_supplier(tenant_a.company, name="S1", state="Karnataka", gstin="29AABCU9603R1ZJ")
    product = make_product(tenant_a.company, sku="RCM2", hsn_code="9983")
    created = tenant_a.client.post(
        "/api/v1/purchases/invoices/",
        {
            "supplier": supplier.id,
            "purchase_type": "GST",
            "invoice_date": PERIOD + "-12",
            "is_reverse_charge": False,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18"}],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    done = tenant_a.client.post(f"/api/v1/purchases/invoices/{created.data['id']}/complete/")
    assert done.status_code == 200, done.data
    assert Decimal(done.data["cgst_total"]) + Decimal(done.data["sgst_total"]) > 0
    toggled = tenant_a.client.patch(
        f"/api/v1/purchases/invoices/{created.data['id']}/",
        {"is_reverse_charge": True, "confirm_amend": True},
        format="json",
    )
    assert toggled.status_code == 200, toggled.data
    assert Decimal(toggled.data["rcm_taxable"]) == Decimal("1000.00")
    assert Decimal(toggled.data["cgst_total"]) == Decimal("0.00")
    assert Decimal(toggled.data["grand_total"]) in (Decimal("1000.00"), Decimal("1000"))
