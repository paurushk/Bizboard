"""GSTR-1 / GSTR-3B offline export tests."""

from decimal import Decimal

import pytest

from sales.models import SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, create_draft_purchase, make_customer, make_product, make_supplier

pytestmark = pytest.mark.django_db

PERIOD = "2026-07"


def _complete_invoice(tenant, customer, product, *, invoice_date=PERIOD + "-15", invoice_type="GST", unit_price="1000"):
    payload = {
        "customer": customer.id,
        "invoice_type": invoice_type,
        "invoice_date": invoice_date,
        "items": [{"product": product.id, "quantity": "1", "unit_price": unit_price, "gst_rate": "18"}],
    }
    resp = tenant.client.post("/api/v1/sales/invoices/", payload, format="json")
    assert resp.status_code == 201, resp.data
    done = tenant.client.post(f"/api/v1/sales/invoices/{resp.data['id']}/complete/")
    assert done.status_code == 200, done.data
    return done.data


def _complete_credit_note(tenant, customer, invoice_id, product):
    cn = tenant.client.post(
        "/api/v1/sales/credit-notes/",
        {
            "customer": customer.id,
            "sales_invoice": invoice_id,
            "note_date": PERIOD + "-20",
            "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "200", "gst_rate": "18"}],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    done = tenant.client.post(f"/api/v1/sales/credit-notes/{cn.data['id']}/complete/")
    assert done.status_code == 200, done.data
    return cn.data


def _setup_gst_month(tenant):
    tenant.company.gstin = "29ABCDE1234F1ZW"
    tenant.company.state = "Karnataka"
    tenant.company.save(update_fields=["gstin", "state"])

    product = make_product(tenant.company, sku="GST-P1")
    add_stock(tenant, product, "100")

    b2b_customer = make_customer(
        tenant.company,
        name="Registered Traders",
        state="Karnataka",
        gstin="29AABCU9603R1ZJ",
    )
    b2c_customer = make_customer(tenant.company, name="Walk-in Buyer", state="Karnataka")
    b2cl_customer = make_customer(tenant.company, name="Delhi Buyer", state="Delhi")

    b2b_inv = _complete_invoice(tenant, b2b_customer, product)
    b2c_inv = _complete_invoice(tenant, b2c_customer, product, invoice_date=PERIOD + "-10")
    b2cl_inv = _complete_invoice(
        tenant,
        b2cl_customer,
        product,
        invoice_date=PERIOD + "-12",
    )
    big_done = _complete_invoice(
        tenant,
        b2cl_customer,
        product,
        invoice_date=PERIOD + "-18",
        unit_price="260000",  # GAP-004: above ₹2.5L B2CL threshold
    )

    _complete_invoice(tenant, b2b_customer, product, invoice_date=PERIOD + "-05")
    _complete_credit_note(tenant, b2b_customer, b2b_inv["id"], product)

    _complete_invoice(tenant, b2c_customer, product, invoice_date=PERIOD + "-22", invoice_type="NON_GST", unit_price="500")

    return b2b_inv, b2c_inv, b2cl_inv, big_done


def test_gstr1_json_shape_and_totals(tenant_a):
    _setup_gst_month(tenant_a)
    resp = tenant_a.client.get("/api/v1/reports/gstr1/", {"period": PERIOD})
    assert resp.status_code == 200, resp.data
    data = resp.data

    for key in ("b2b", "b2cl", "b2cs", "cdnr", "docs", "totals", "period", "company"):
        assert key in data
    assert data["period"] == PERIOD
    assert len(data["b2b"]) >= 2
    assert len(data["b2cl"]) >= 1
    assert len(data["b2cs"]) >= 1
    assert len(data["cdnr"]) == 1
    assert data["docs"]["credit_notes_issued"] == 1

    register = tenant_a.client.get(
        "/api/v1/reports/sales-register/",
        {"date_from": "2026-07-01", "date_to": "2026-07-31"},
    )
    assert register.status_code == 200
    register_taxable = Decimal(str(register.data["totals"]["taxable"]))
    non_gst_rows = [row for row in register.data["rows"] if row.get("invoice_type") == "NON_GST"]
    register_taxable -= sum(Decimal(str(row["taxable"])) for row in non_gst_rows)

    assert Decimal(data["totals"]["outward_taxable"]) == register_taxable


def test_gstr3b_json_and_xlsx_export(tenant_a):
    _setup_gst_month(tenant_a)
    resp = tenant_a.client.get("/api/v1/reports/gstr3b/", {"period": PERIOD})
    assert resp.status_code == 200, resp.data
    data = resp.data
    assert data["return_type"] == "GSTR-3B"
    assert "outward_supplies" in data
    assert "inward_supplies" in data
    assert "itc" in data
    assert len(data["itc"]["manual_review"]) >= 1

    xlsx = tenant_a.client.get("/api/v1/reports/gstr3b/", {"period": PERIOD, "format": "xlsx"})
    assert xlsx.status_code == 200
    assert "spreadsheetml" in xlsx["Content-Type"]
    assert len(xlsx.content) > 100


def test_gstr1_excludes_opening_balance_invoices(tenant_a):
    """BB-000335: Tally-migrated opening-balance invoices must never distort
    live GSTR-1 totals/sections."""
    b2b_inv, *_ = _setup_gst_month(tenant_a)
    baseline = tenant_a.client.get("/api/v1/reports/gstr1/", {"period": PERIOD})
    assert baseline.status_code == 200
    baseline_taxable = Decimal(str(baseline.data["totals"]["outward_taxable"]))
    baseline_b2b = len(baseline.data["b2b"])

    invoice = SalesInvoice.objects.get(pk=b2b_inv["id"])
    invoice.is_opening_balance = True
    invoice.save(update_fields=["is_opening_balance"])

    resp = tenant_a.client.get("/api/v1/reports/gstr1/", {"period": PERIOD})
    assert resp.status_code == 200, resp.data
    new_taxable = Decimal(str(resp.data["totals"]["outward_taxable"]))
    assert new_taxable < baseline_taxable
    assert len(resp.data["b2b"]) < baseline_b2b


def test_gstr3b_excludes_opening_balance_purchase(tenant_a):
    """BB-000335: opening-balance purchase invoices must not inflate GSTR-3B
    ITC/inward figures."""
    _setup_gst_month(tenant_a)
    baseline = tenant_a.client.get("/api/v1/reports/gstr3b/", {"period": PERIOD})
    assert baseline.status_code == 200
    baseline_itc = Decimal(str(baseline.data["itc"]["available_from_purchases"]["total_tax"]))

    supplier = make_supplier(tenant_a.company, name="Opening Supplier", gstin="29AABCU9603R1ZJ")
    product = make_product(tenant_a.company, sku="GST-OPEN")
    pur = create_draft_purchase(
        tenant_a, supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200

    from purchases.models import PurchaseInvoice

    invoice = PurchaseInvoice.objects.get(pk=pur["id"])
    invoice.invoice_date = PERIOD + "-10"
    invoice.is_opening_balance = True
    invoice.save(update_fields=["invoice_date", "is_opening_balance"])

    resp = tenant_a.client.get("/api/v1/reports/gstr3b/", {"period": PERIOD})
    assert resp.status_code == 200, resp.data
    new_itc = Decimal(str(resp.data["itc"]["available_from_purchases"]["total_tax"]))
    assert new_itc == baseline_itc


def test_gstr1_cdnr_excludes_value_mismatched_note(tenant_a):
    """BB-000361: a credit note whose grand_total doesn't reconcile to
    taxable+tax (AFTER_TAX discount) must be excluded from CDNR and flagged
    as an issue instead of silently distorting section totals."""
    b2b_inv, *_ = _setup_gst_month(tenant_a)
    invoice = SalesInvoice.objects.get(pk=b2b_inv["id"])
    product_id = invoice.items.first().product_id
    cn = tenant_a.client.post(
        "/api/v1/sales/credit-notes/",
        {
            "customer": invoice.customer_id,
            "sales_invoice": b2b_inv["id"],
            "note_date": PERIOD + "-21",
            "reason": "CORRECTION_OF_INVOICE",
            "invoice_discount": "50",
            "items": [{"product": product_id, "quantity": "1", "unit_price": "200", "gst_rate": "18"}],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    done = tenant_a.client.post(f"/api/v1/sales/credit-notes/{cn.data['id']}/complete/")
    assert done.status_code == 200, done.data

    resp = tenant_a.client.get("/api/v1/reports/gstr1/", {"period": PERIOD})
    assert resp.status_code == 200, resp.data
    cdnr_numbers = {row["note_number"] for row in resp.data["cdnr"]}
    assert done.data["number"] not in cdnr_numbers
    assert any(
        issue["code"] == "INVOICE_VALUE_MISMATCH" and issue["number"] == done.data["number"]
        for issue in resp.data["issues"]
    )


def test_gstr_export_requires_can_export(tenant_a):
    _setup_gst_month(tenant_a)
    resp = tenant_a.staff_client.get("/api/v1/reports/gstr1/", {"period": PERIOD, "format": "xlsx"})
    assert resp.status_code == 403

    preview = tenant_a.staff_client.get("/api/v1/reports/gstr1/", {"period": PERIOD})
    assert preview.status_code == 403
