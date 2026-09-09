"""A-03: preview_totals matches Complete for inclusive + cess + freight."""

from decimal import Decimal

import pytest

from sales.models import SalesInvoice
from tests.conftest import add_stock, make_customer, make_product

pytestmark = pytest.mark.django_db

PERIOD = "2026-08"


def test_preview_totals_matches_complete_inclusive_cess_freight(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    product = make_product(tenant_a.company, sku="A03", hsn_code="3004", gst_rate="18")
    add_stock(tenant_a, product, "5")
    cust = make_customer(tenant_a.company, name="B2B", state="Karnataka", gstin="29AABCU9603R1ZJ")
    payload = {
        "customer": cust.id,
        "invoice_type": "GST",
        "invoice_date": PERIOD + "-15",
        "price_mode": "INCLUSIVE",
        "additional_charges": "50",
        "auto_round_off": True,
        "items": [{
            "product": product.id,
            "quantity": "1",
            "unit_price": "118",
            "unit_price_inclusive": "118",
            "gst_rate": "18",
            "cess_rate": "1",
        }],
    }
    preview = tenant_a.client.post("/api/v1/sales/invoices/preview-totals/", payload, format="json")
    assert preview.status_code == 200, preview.data
    created = tenant_a.client.post("/api/v1/sales/invoices/", payload, format="json")
    assert created.status_code == 201, created.data
    completed = tenant_a.client.post(f"/api/v1/sales/invoices/{created.data['id']}/complete/")
    assert completed.status_code == 200, completed.data
    inv = SalesInvoice.objects.get(pk=created.data["id"])
    assert Decimal(str(preview.data["grand_total"])) == Decimal(str(inv.grand_total))
    assert Decimal(str(preview.data["cess_total"])) == Decimal(str(inv.cess_total))
    assert Decimal(str(preview.data["cgst_total"])) == Decimal(str(inv.cgst_total))
    assert Decimal(str(completed.data["grand_total"])) == Decimal(str(inv.grand_total))


def test_preview_honors_explicit_tcs_amount_including_zero(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    product = make_product(tenant_a.company, sku="A03-TCS", hsn_code="1001", gst_rate="18")
    add_stock(tenant_a, product, "5")
    cust = make_customer(tenant_a.company, name="B2B", state="Karnataka", gstin="29AABCU9603R1ZJ")
    payload = {
        "customer": cust.id,
        "invoice_type": "GST",
        "invoice_date": PERIOD + "-15",
        "tcs_rate": "0.100",
        "tcs_amount": "0",
        "items": [
            {
                "product": product.id,
                "quantity": "1",
                "unit_price": "1000",
                "gst_rate": "18",
            }
        ],
    }
    preview = tenant_a.client.post("/api/v1/sales/invoices/preview-totals/", payload, format="json")
    assert preview.status_code == 200, preview.data
    assert Decimal(str(preview.data["tcs_amount"])) == Decimal("0")
    created = tenant_a.client.post("/api/v1/sales/invoices/", payload, format="json")
    assert created.status_code == 201, created.data
    completed = tenant_a.client.post(f"/api/v1/sales/invoices/{created.data['id']}/complete/")
    assert completed.status_code == 200, completed.data
    inv = SalesInvoice.objects.get(pk=created.data["id"])
    assert inv.tcs_amount_manual is True
    assert Decimal(str(inv.tcs_amount)) == Decimal("0")


def test_preview_includes_rcm_cess_and_rcm_cgst(tenant_a):
    """R-027: preview JSON includes rcm_cess / rcm_cgst after apply_rcm_memo_after_tax."""
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    from tests.conftest import make_supplier

    product = make_product(tenant_a.company, sku="A03-RCM", hsn_code="9983", gst_rate="18")
    supplier = make_supplier(tenant_a.company, name="RCM Sup", state="Karnataka", gstin="")
    payload = {
        "supplier": supplier.id,
        "purchase_type": "GST",
        "is_reverse_charge": True,
        "invoice_date": PERIOD + "-15",
        "items": [{
            "product": product.id,
            "quantity": "1",
            "unit_price": "1000",
            "gst_rate": "18",
            "cess_rate": "1",
        }],
    }
    preview = tenant_a.client.post(
        "/api/v1/purchases/invoices/preview-totals/", payload, format="json"
    )
    assert preview.status_code == 200, preview.data
    assert Decimal(str(preview.data["cgst_total"])) == Decimal("0")
    assert Decimal(str(preview.data["rcm_cgst"])) == Decimal("90.00")
    assert Decimal(str(preview.data["rcm_sgst"])) == Decimal("90.00")
    assert Decimal(str(preview.data["rcm_cess"])) == Decimal("10.00")
    assert Decimal(str(preview.data["grand_total"])) == Decimal("1000.00")


def test_rcm_rezero_clears_line_cess(tenant_a):
    """R-032: Complete re-zero path clears leftover line cess on an RCM bill."""
    from purchases.models import PurchaseInvoice
    from tests.conftest import create_draft_purchase, make_supplier

    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    supplier = make_supplier(tenant_a.company, name="RCM Rezero", state="Karnataka", gstin="")
    product = make_product(tenant_a.company, sku="RCM-CESS", hsn_code="9983", gst_rate="18")
    draft = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18", "cess_rate": "1"}],
    )
    tenant_a.client.patch(
        f"/api/v1/purchases/invoices/{draft['id']}/",
        {"is_reverse_charge": True},
        format="json",
    )
    inv = PurchaseInvoice.objects.get(pk=draft["id"])
    item = inv.items.get()
    item.cess = Decimal("10.00")
    item.save(update_fields=["cess"])
    assert Decimal(str(item.cess)) == Decimal("10.00")
    done = tenant_a.client.post(f"/api/v1/purchases/invoices/{draft['id']}/complete/")
    assert done.status_code == 200, done.data
    item.refresh_from_db()
    assert Decimal(str(item.cess)) == Decimal("0.00")
    inv.refresh_from_db()
    assert inv.rcm_cess == Decimal("10.00")
    assert inv.cess_total == Decimal("0.00")
    data = done.data
    assert Decimal(str(data.get("rcmCess") or data.get("rcm_cess") or 0)) == Decimal("10.00")


def test_preview_and_complete_tcs_rate_without_amount_folds(tenant_a):
    """R-001: omitting tcs_amount lets rate math run."""
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save()
    product = make_product(tenant_a.company, sku="A03-TCS-RATE", hsn_code="1001", gst_rate="18")
    add_stock(tenant_a, product, "5")
    cust = make_customer(tenant_a.company, name="B2B-TCS", state="Karnataka", gstin="29AABCU9603R1ZJ")
    payload = {
        "customer": cust.id,
        "invoice_type": "GST",
        "invoice_date": PERIOD + "-15",
        "tcs_section": "206C",
        "tcs_rate": "0.1",
        "items": [
            {
                "product": product.id,
                "quantity": "1",
                "unit_price": "100000",
                "gst_rate": "18",
            }
        ],
    }
    preview = tenant_a.client.post("/api/v1/sales/invoices/preview-totals/", payload, format="json")
    assert preview.status_code == 200, preview.data
    assert Decimal(str(preview.data["tcs_amount"])) > Decimal("0")
    created = tenant_a.client.post("/api/v1/sales/invoices/", payload, format="json")
    assert created.status_code == 201, created.data
    completed = tenant_a.client.post(f"/api/v1/sales/invoices/{created.data['id']}/complete/")
    assert completed.status_code == 200, completed.data
    inv = SalesInvoice.objects.get(pk=created.data["id"])
    assert inv.tcs_amount_manual is False
    assert Decimal(str(inv.tcs_amount)) > Decimal("0")
