"""WP-DL1: readable, versioned customer export (CSV + PDF ZIP with a manifest)."""

import hashlib
import io
import json
import os
import zipfile
from datetime import timedelta
from pathlib import Path

import pytest
from django.utils import timezone

from accounts.models import ReadableExport
from accounts.readable_export import FORMAT_VERSION, build_readable_zip, purge_expired
from masters.models import Customer, Supplier

pytestmark = pytest.mark.django_db

SNAPSHOT = Path(__file__).parent / "snapshots" / "readable_export_columns.json"
# The sections whose columns customers and their accountants build on. Changing these needs a
# format version bump (docs/help/DATA_EXPORT_FORMAT.md); re-record with UPDATE_EXPORT_SNAPSHOT=1.
PINNED = ("customers", "suppliers", "products", "sales_invoices", "sales_items", "purchase_invoices",
          "purchase_items", "receipts", "supplier_payments", "accounts", "journals", "journal_lines")


def _seed(tenant):
    Customer.objects.create(company=tenant.company, name="ग्राहक एक", phone="9820011111")
    Customer.objects.create(company=tenant.company, name="Second Buyer")
    Supplier.objects.create(company=tenant.company, name="Supplier One")


def _seed_documents(tenant):
    """Rows in the document sections too, so their columns are pinned (an empty section has no
    header row to compare, and the snapshot used to record ``[]`` for all of them)."""
    from tests.conftest import add_stock, create_draft_invoice, create_draft_purchase, make_product

    product = make_product(tenant.company, name="Pinned Item", sku="PIN-1")
    add_stock(tenant, product, "10")
    buyer = Customer.objects.filter(company=tenant.company, name="Second Buyer").first()
    supplier = Supplier.objects.filter(company=tenant.company, name="Supplier One").first()
    line = [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}]
    invoice = create_draft_invoice(tenant, buyer, line)
    tenant.client.post(f"/api/v1/sales/invoices/{invoice['id']}/complete/", {}, format="json")
    create_draft_purchase(tenant, supplier, [{"product": product.id, "quantity": "1", "unit_price": "80",
                                              "gst_rate": "18"}])
    tenant.client.post("/api/v1/payments/receipts/", {"customer": buyer.id, "amount": "50", "mode": "CASH"},
                       format="json")
    tenant.client.post("/api/v1/payments/supplier-payments/", {"supplier": supplier.id, "amount": "40",
                                                               "mode": "CASH"}, format="json")


def _open(blob):
    zf = zipfile.ZipFile(io.BytesIO(blob))
    return zf, json.loads(zf.read("manifest.json"))


def test_manifest_counts_match_the_database_and_checksums_verify(tenant_a):
    _seed(tenant_a)
    blob, _ = build_readable_zip(tenant_a.company)
    zf, manifest = _open(blob)
    assert manifest["format"] == "bizboard-readable-export" and manifest["format_version"] == FORMAT_VERSION
    by_name = {f["name"]: f for f in manifest["files"]}
    assert by_name["customers.csv"]["rows"] == Customer.objects.filter(company=tenant_a.company).count()
    assert by_name["suppliers.csv"]["rows"] == 1
    for f in manifest["files"]:
        assert hashlib.sha256(zf.read(f["name"])).hexdigest() == f["sha256"], f["name"]
    customers = zf.read("customers.csv")
    assert customers.startswith(b"\xef\xbb\xbf")  # BOM: Excel shows Hindi correctly
    assert "ग्राहक एक" in customers.decode("utf-8-sig")
    readme = zf.read("README.txt").decode("utf-8")
    assert "Bizboard data export" in readme and "डेटा निर्यात" in readme


def test_other_companies_rows_never_appear(tenant_a, tenant_b):
    _seed(tenant_a)
    Customer.objects.create(company=tenant_b.company, name="Not Yours Ltd")
    blob, _ = build_readable_zip(tenant_a.company)
    zf, _ = _open(blob)
    assert "Not Yours Ltd" not in zf.read("customers.csv").decode("utf-8-sig")


def test_pinned_columns_match_the_snapshot(tenant_a):
    _seed(tenant_a)
    _seed_documents(tenant_a)
    blob, _ = build_readable_zip(tenant_a.company)
    zf, _ = _open(blob)
    got = {}
    for section in PINNED:
        text = zf.read(f"{section}.csv").decode("utf-8-sig")
        got[section] = text.splitlines()[0].split(",") if text else []
    if os.environ.get("UPDATE_EXPORT_SNAPSHOT") == "1":
        SNAPSHOT.parent.mkdir(exist_ok=True)
        SNAPSHOT.write_text(json.dumps({"format_version": FORMAT_VERSION, "columns": got}, indent=2) + "\n",
                            encoding="utf-8")
    pinned = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert pinned["format_version"] == FORMAT_VERSION, "bump the snapshot with the format version"
    for section in PINNED:
        assert pinned["columns"].get(section), f"{section} has no pinned columns: seed a row for it"
    for section, cols in pinned["columns"].items():
        assert got[section] == cols, (
            f"{section} columns changed: bump FORMAT_VERSION (minor for added, major for renamed or "
            "removed) and re-record with UPDATE_EXPORT_SNAPSHOT=1"
        )


def test_only_the_owner_can_ask_and_the_request_is_on_the_privacy_register(tenant_a):
    from support.models import DataPrivacyRequest

    assert tenant_a.staff_client.post("/api/v1/company/export/readable/", {"password": "StrongPass123!"},
                                      format="json").status_code == 403
    assert tenant_a.client.post("/api/v1/company/export/readable/", {}, format="json").status_code in (400, 403)
    resp = tenant_a.client.post("/api/v1/company/export/readable/", {"password": "StrongPass123!"}, format="json")
    assert resp.status_code == 202, resp.content
    row = ReadableExport.objects.get(company=tenant_a.company)
    assert row.status == ReadableExport.Status.READY  # Celery runs eagerly in tests
    assert DataPrivacyRequest.objects.filter(company_id_hint=tenant_a.company.pk, kind="ACCESS").exists()
    listed = tenant_a.client.get("/api/v1/company/export/readable/").json()["data"]
    assert listed[0]["status"] == "READY" and listed[0]["formatVersion"] == FORMAT_VERSION
    got = tenant_a.client.get(f"/api/v1/company/export/readable/{row.pk}/file/")
    assert got.status_code == 200 and got["Content-Type"] == "application/zip"
    zipfile.ZipFile(io.BytesIO(b"".join(got.streaming_content))).read("manifest.json")


def test_link_expires_and_the_file_is_purged(tenant_a):
    tenant_a.client.post("/api/v1/company/export/readable/", {"password": "StrongPass123!"}, format="json")
    row = ReadableExport.objects.get(company=tenant_a.company)
    ReadableExport.objects.filter(pk=row.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
    assert tenant_a.client.get(f"/api/v1/company/export/readable/{row.pk}/file/").status_code == 410
    assert purge_expired() == 1
    row.refresh_from_db()
    assert row.status == ReadableExport.Status.EXPIRED


def test_another_companys_export_is_not_found(tenant_a, tenant_b):
    tenant_a.client.post("/api/v1/company/export/readable/", {"password": "StrongPass123!"}, format="json")
    row = ReadableExport.objects.get(company=tenant_a.company)
    assert tenant_b.client.get(f"/api/v1/company/export/readable/{row.pk}/file/").status_code == 404
