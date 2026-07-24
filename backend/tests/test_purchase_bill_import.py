"""Purchase bill upload — LLM extract → preview → draft purchase commit."""

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from inventory.models import StockBalance, StockMovement
from masters.models import Product, Supplier
from purchases.models import PurchaseInvoice
from tests.conftest import make_product, make_supplier

pytestmark = pytest.mark.django_db

FAKE_EXTRACT = {
    "supplier_name": "Acme Distributors",
    "supplier_gstin": "",
    "bill_number": "PB-100",
    "bill_date": "2026-07-01",
    "lines": [
        {
            "name": "Ariel Powder 500g",
            "sku": "ARIEL-500",
            "hsn_code": "3402",
            "quantity": "2",
            "unit_price": "120.50",
            "gst_rate": "18",
            "mrp": "150",
        },
        {
            "name": "Baby Rub 10ml",
            "sku": "",
            "hsn_code": "3004",
            "quantity": "5",
            "unit_price": "45",
            "gst_rate": "12",
            "mrp": "0",
        },
    ],
}


def _png_bytes():
    # Minimal 1x1 PNG
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def _upload_bill(tenant, content=None, name="bill.png", content_type="image/png", supplier_id=None):
    data = {
        "kind": "PURCHASE_BILL",
        "file": SimpleUploadedFile(name, content or _png_bytes(), content_type=content_type),
    }
    if supplier_id is not None:
        data["supplier_id"] = supplier_id
    return tenant.client.post("/api/v1/imports/", data, format="multipart")


@patch("core.services.llm.extract_purchase_bill", return_value=FAKE_EXTRACT)
def test_purchase_bill_extract_preview(mock_llm, tenant_a):
    resp = _upload_bill(tenant_a)
    assert resp.status_code == 201, resp.data
    assert resp.data["status"] == "PREVIEWED"
    assert resp.data["valid_rows"] == 2
    preview = resp.data["preview"]
    assert preview["bill_number"] == "PB-100"
    assert len(preview["lines"]) == 2
    mock_llm.assert_called_once()


@patch("core.services.llm.extract_purchase_bill", return_value=FAKE_EXTRACT)
def test_purchase_bill_commit_creates_products_and_draft(mock_llm, tenant_a):
    supplier = make_supplier(tenant_a.company, name="Existing Supplier")
    job = _upload_bill(tenant_a, supplier_id=supplier.id).data
    assert job["status"] == "PREVIEWED"

    resp = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert resp.status_code == 200, resp.data
    assert resp.data["created"] == 2
    assert resp.data["products_created"] == 2
    assert resp.data["purchase_invoice_id"]

    assert Product.objects.filter(company=tenant_a.company, sku="ARIEL-500").exists()
    assert Product.objects.filter(company=tenant_a.company, name="Baby Rub 10ml").exists()

    invoice = PurchaseInvoice.objects.get(pk=resp.data["purchase_invoice_id"])
    assert invoice.status == PurchaseInvoice.Status.DRAFT
    assert invoice.supplier_id == supplier.id
    assert invoice.items.count() == 2
    assert invoice.supplier_bill_number == "PB-100"

    # Stock unchanged until Complete
    assert StockMovement.objects.filter(company=tenant_a.company).count() == 0
    assert StockBalance.objects.filter(company=tenant_a.company).count() == 0


@patch("core.services.llm.extract_purchase_bill", return_value=FAKE_EXTRACT)
def test_purchase_bill_matches_existing_product(mock_llm, tenant_a):
    make_product(tenant_a.company, name="Ariel Powder 500g", sku="ARIEL-500", purchase_price="100")
    supplier = make_supplier(tenant_a.company)
    job = _upload_bill(tenant_a, supplier_id=supplier.id).data

    resp = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert resp.status_code == 200
    assert resp.data["products_created"] == 1  # only Baby Rub is new
    product = Product.objects.get(company=tenant_a.company, sku="ARIEL-500")
    # Matched products keep master purchase_price (OCR must not overwrite).
    assert product.purchase_price == Decimal("100")


@patch("core.services.llm.extract_purchase_bill", return_value=FAKE_EXTRACT)
def test_purchase_bill_preview_edit_excludes_line(mock_llm, tenant_a):
    supplier = make_supplier(tenant_a.company)
    job = _upload_bill(tenant_a, supplier_id=supplier.id).data
    preview = job["preview"]
    preview["lines"][1]["include"] = False

    patched = tenant_a.client.patch(
        f"/api/v1/imports/{job['id']}/preview/",
        {"lines": preview["lines"], "supplier_id": supplier.id},
        format="json",
    )
    assert patched.status_code == 200
    assert patched.data["valid_rows"] == 1

    resp = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert resp.status_code == 200
    assert resp.data["created"] == 1
    invoice = PurchaseInvoice.objects.get(pk=resp.data["purchase_invoice_id"])
    assert invoice.items.count() == 1


@patch("core.services.llm.extract_purchase_bill", side_effect=Exception("provider down"))
def test_purchase_bill_extraction_failure(mock_llm, tenant_a):
    resp = _upload_bill(tenant_a)
    assert resp.status_code == 201
    assert resp.data["status"] == "FAILED"
    assert "provider down" in (resp.data.get("failure_reason") or "")


def test_purchase_bill_rejects_csv(tenant_a):
    resp = tenant_a.client.post("/api/v1/imports/", {
        "kind": "PURCHASE_BILL",
        "file": SimpleUploadedFile("data.csv", b"name\nSoap\n", content_type="text/csv"),
    }, format="multipart")
    assert resp.status_code == 400


@patch("core.services.llm.extract_purchase_bill", return_value=FAKE_EXTRACT)
def test_purchase_bill_creates_supplier_from_extracted_name(mock_llm, tenant_a):
    job = _upload_bill(tenant_a).data
    resp = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert resp.status_code == 200, resp.data
    assert Supplier.objects.filter(company=tenant_a.company, name="Acme Distributors").exists()


@patch("core.services.llm.extract_purchase_bill", return_value=FAKE_EXTRACT)
def test_purchase_bill_rejects_unparseable_date(mock_llm, tenant_a):
    supplier = make_supplier(tenant_a.company)
    job = _upload_bill(tenant_a, supplier_id=supplier.id).data
    preview = job["preview"]
    preview["bill_date"] = "not-a-date"
    patched = tenant_a.client.patch(
        f"/api/v1/imports/{job['id']}/preview/",
        {"bill_date": "not-a-date", "lines": preview["lines"], "supplier_id": supplier.id},
        format="json",
    )
    assert patched.status_code == 200
    resp = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert resp.status_code == 400
    assert "bill date" in str(resp.data).lower() or "parse" in str(resp.data).lower()


@patch("core.services.llm.extract_purchase_bill", side_effect=Exception("provider down"))
def test_purchase_bill_retry_extract(mock_fail, tenant_a):
    job = _upload_bill(tenant_a).data
    assert job["status"] == "FAILED"
    with patch("core.services.llm.extract_purchase_bill", return_value=FAKE_EXTRACT) as mock_ok:
        resp = tenant_a.client.post(f"/api/v1/imports/{job['id']}/retry-extract/")
        assert resp.status_code == 200, resp.data
        assert resp.data["status"] == "PREVIEWED"
        mock_ok.assert_called_once()
