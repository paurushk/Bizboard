"""MIME sniff acceptance for Excel-friendly CSV uploads."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import FileAsset
from core.services.files import FileService, _sniff_mime

pytestmark = pytest.mark.django_db


def test_sniff_accepts_utf8_bom_csv():
    header = b"\xef\xbb\xbf" + b"name,sku,barcode,hsn"
    assert _sniff_mime(header, "products.csv", "text/csv") == "text/csv"


def test_sniff_accepts_ms_excel_declared_text_csv():
    header = b"name,sku,quantity,unit_cost\nr"
    assert _sniff_mime(header, "stock.csv", "application/vnd.ms-excel") == "text/csv"


def test_sniff_accepts_empty_ctype_with_csv_extension():
    header = b"name,sku\nSoap,S1"
    assert _sniff_mime(header, "data.csv", "") == "text/csv"


def test_sniff_accepts_devanagari_in_first_bytes():
    header = ("name," + "साबुन").encode("utf-8")
    assert _sniff_mime(header, "p.csv", "text/csv") == "text/csv"


def test_sniff_accepts_rupee_early():
    header = ("name\n" + "₹ Soap").encode("utf-8")
    assert _sniff_mime(header, "p.csv", "text/csv") == "text/csv"


def test_validate_upload_accepts_bom_csv():
    content = b"\xef\xbb\xbfname,sku\nSoap,S1\n"
    uploaded = SimpleUploadedFile("data.csv", content, content_type="text/csv")
    sniffed = FileService.validate_upload(uploaded_file=uploaded, kind=FileAsset.Kind.IMPORT)
    assert sniffed == "text/csv"


def test_validate_upload_accepts_cp1252_csv(tenant_a):
    """Windows-1252/ANSI CSV (Excel default) is accepted and decoded."""
    # First 32+ bytes ASCII so sniff accepts; 0xE9 (é in cp1252) appears later.
    content = b"name,sku,gst_rate,selling_price,hsn_code\nCaf\xe9,S1,18,40,3401\n"
    uploaded = SimpleUploadedFile("data.csv", content, content_type="text/csv")
    sniffed = FileService.validate_upload(uploaded_file=uploaded, kind=FileAsset.Kind.IMPORT)
    assert sniffed == "text/csv"
    resp = tenant_a.client.post(
        "/api/v1/imports/",
        {"kind": "products", "file": SimpleUploadedFile("data.csv", content, content_type="text/csv")},
        format="multipart",
    )
    assert resp.status_code == 201, resp.data
    assert resp.data["valid_rows"] == 1


def test_sniff_accepts_cp1252_accented_header():
    header = "Café,sku,barcode,hsn".encode("cp1252")
    assert _sniff_mime(header, "products.csv", "text/csv") == "text/csv"
