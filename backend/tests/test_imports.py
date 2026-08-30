"""Import pipeline — Upload → Validate → Preview → Commit → Error report (§15)."""

from decimal import Decimal
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import FileAsset
from imports.models import ImportJob
from masters.models import Customer, Product
from tests.conftest import make_product

pytestmark = pytest.mark.django_db

CUSTOMERS_CSV = (
    b"name,phone,gstin,state\n"
    b"Ravi Stores,9800000001,,Karnataka\n"
    b"Meena Traders,9800000002,29ABCDE1234F1ZW,Karnataka\n"
    b",9800000003,,Karnataka\n"          # missing name → error
    b"Bad GSTIN Shop,9800000004,NOTAGSTIN,Karnataka\n"  # invalid gstin → error
)


def _upload(tenant, kind, content, name="data.csv", content_type="text/csv"):
    return tenant.client.post("/api/v1/imports/", {
        "kind": kind,
        "file": SimpleUploadedFile(name, content, content_type=content_type),
    }, format="multipart")


def test_preview_reports_valid_and_error_rows(tenant_a):
    resp = _upload(tenant_a, "customers", CUSTOMERS_CSV)
    assert resp.status_code == 201, resp.data
    assert resp.data["status"] == "PREVIEWED"
    assert resp.data["total_rows"] == 4
    assert resp.data["valid_rows"] == 2
    assert resp.data["error_rows"] == 2
    assert Customer.objects.filter(company=tenant_a.company).count() == 0  # no blind import


def test_commit_writes_only_valid_rows(tenant_a):
    job = _upload(tenant_a, "customers", CUSTOMERS_CSV).data
    resp = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert resp.status_code == 200
    assert resp.data["created"] == 2
    assert Customer.objects.filter(company=tenant_a.company).count() == 2

    errors = tenant_a.client.get(f"/api/v1/imports/{job['id']}/errors/")
    assert errors.data["error_rows"] == 2


def test_staff_without_permission_cannot_commit(tenant_a):
    job = _upload(tenant_a, "customers", CUSTOMERS_CSV).data
    resp = tenant_a.staff_client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert resp.status_code == 403


def test_opening_stock_import(tenant_a):
    make_product(tenant_a.company, sku="SKU-1")
    csv_content = b"sku,quantity,unit_cost\nSKU-1,25,80\nMISSING,5,10\n"
    job = _upload(tenant_a, "opening_stock", csv_content).data
    assert job["valid_rows"] == 1
    assert job["error_rows"] == 1

    resp = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert resp.status_code == 200
    from inventory.models import StockBalance

    balance = StockBalance.objects.get(company=tenant_a.company)
    assert balance.on_hand == Decimal("25")


def test_products_import(tenant_a):
    csv_content = (
        b"name,sku,gst_rate,selling_price,hsn_code\n"
        b"Soap,SOAP-1,18,45,3401\n"
        b"Bad Rate,BAD-1,17,10,3401\n"
    )
    job = _upload(tenant_a, "products", csv_content).data
    resp = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert resp.status_code == 400
    assert not Product.objects.filter(company=tenant_a.company, sku="SOAP-1").exists()
    assert not Product.objects.filter(company=tenant_a.company, sku="BAD-1").exists()


def test_missing_required_column_rejected(tenant_a):
    resp = _upload(tenant_a, "customers", b"phone\n9800000001\n")
    assert resp.status_code == 400


def test_products_import_with_unit_and_opening_stock(tenant_a):
    csv_content = (
        b"name,sku,gst_rate,selling_price,hsn_code,unit,opening_stock,unit_cost\n"
        b"Green Tea,TEA-1,5,150,0902,PCS,50,90\n"
    )
    job = _upload(tenant_a, "products", csv_content).data
    assert job["valid_rows"] == 1
    assert job["error_rows"] == 0

    resp = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert resp.status_code == 200
    assert resp.data["created"] == 1

    product = Product.objects.get(company=tenant_a.company, sku="TEA-1")
    assert product.unit is not None
    assert product.unit.short_name == "PCS"

    from inventory.models import StockBalance
    balance = StockBalance.objects.get(company=tenant_a.company, product=product)
    assert balance.on_hand == Decimal("50")


def test_products_import_zero_opening_stock_is_catalog_only(tenant_a):
    csv_content = (
        b"name,sku,gst_rate,selling_price,opening_stock,unit_cost\n"
        b"Catalog Only,CAT-0,0,80,0,40\n"
        b"Negative Qty,NEG-1,0,80,-1,40\n"
    )
    job = _upload(tenant_a, "products", csv_content).data
    assert job["valid_rows"] == 1
    assert job["error_rows"] == 1
    assert any("opening_stock must be >= 0" in err for err in job["errors"][0]["errors"])

    resp = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert resp.status_code == 400

    csv_ok = (
        b"name,sku,gst_rate,selling_price,opening_stock,unit_cost\n"
        b"Catalog Only,CAT-0,0,80,0,40\n"
    )
    job_ok = _upload(tenant_a, "products", csv_ok).data
    assert job_ok["valid_rows"] == 1
    assert job_ok["error_rows"] == 0
    resp = tenant_a.client.post(f"/api/v1/imports/{job_ok['id']}/commit/")
    assert resp.status_code == 200
    assert resp.data["created"] == 1
    product = Product.objects.get(company=tenant_a.company, sku="CAT-0")
    from inventory.models import StockBalance
    assert not StockBalance.objects.filter(company=tenant_a.company, product=product).exists()


def test_opening_stock_validation_edge_cases(tenant_a):
    make_product(tenant_a.company, sku="SKU-CASE")
    csv_content = (
        b"sku,quantity,unit_cost\n"
        b"sku-case,10,50\n"        # Case-insensitive match -> valid
        b"sku-case,20,50\n"        # Duplicate in file -> error
        b"SKU-CASE,-5,50\n"        # Negative quantity -> error
        b"SKU-CASE,5,-10\n"        # Negative unit_cost -> error
    )
    job = _upload(tenant_a, "opening_stock", csv_content).data
    assert job["valid_rows"] == 1
    assert job["error_rows"] == 3


def test_opening_stock_flags_already_recorded_opening(tenant_a):
    prod = make_product(tenant_a.company, sku="SKU-EXISTING")
    from inventory.models import MovementType
    from inventory.services import InventoryService
    InventoryService.post_movement(
        company=tenant_a.company,
        product=prod,
        movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("10"),
    )

    csv_content = b"sku,quantity,unit_cost\nSKU-EXISTING,25,80\n"
    job = _upload(tenant_a, "opening_stock", csv_content).data
    assert job["valid_rows"] == 0
    assert job["error_rows"] == 1
    assert any("opening stock already recorded" in err for err in job["errors"][0]["errors"])


def test_opening_stock_import_requires_serials_for_tracked_product(tenant_a):
    make_product(tenant_a.company, sku="SER-OS", track_serial=True)
    csv_content = b"sku,quantity,unit_cost\nSER-OS,2,500\n"
    job = _upload(tenant_a, "opening_stock", csv_content).data
    assert job["valid_rows"] == 0
    assert job["error_rows"] == 1
    assert any(
        "Serial numbers are required for serial-tracked opening stock." in err
        for err in job["errors"][0]["errors"]
    )


def test_opening_stock_import_posts_serials(tenant_a):
    make_product(tenant_a.company, sku="SER-OS2", track_serial=True)
    csv_content = b'sku,quantity,unit_cost,serial_no\nSER-OS2,2,500,"SN-A,SN-B"\n'
    job = _upload(tenant_a, "opening_stock", csv_content).data
    assert job["valid_rows"] == 1, job
    assert job["error_rows"] == 0
    resp = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert resp.status_code == 200, resp.data
    from inventory.models import SerialNumber, StockBalance

    product = Product.objects.get(company=tenant_a.company, sku="SER-OS2")
    assert StockBalance.objects.get(company=tenant_a.company, product=product).on_hand == Decimal("2")
    numbers = set(
        SerialNumber.objects.filter(company=tenant_a.company, product=product).values_list(
            "serial_number", flat=True
        )
    )
    assert numbers == {"SN-A", "SN-B"}


def test_products_import_serial_opening_requires_serials(tenant_a):
    csv_content = (
        b"name,sku,gst_rate,selling_price,track_serial,opening_stock,unit_cost\n"
        b"Phone,PH-SN,18,12000,yes,2,8000\n"
    )
    job = _upload(tenant_a, "products", csv_content).data
    assert job["valid_rows"] == 0
    assert job["error_rows"] == 1
    assert any(
        "Serial numbers are required for serial-tracked opening stock." in err
        for err in job["errors"][0]["errors"]
    )


def test_products_import_serial_opening_with_serials(tenant_a):
    csv_content = (
        b"name,sku,gst_rate,selling_price,track_serial,opening_stock,unit_cost,serial_no\n"
        b'Phone,PH-SN2,18,12000,yes,2,8000,"IMEI-1,IMEI-2"\n'
    )
    job = _upload(tenant_a, "products", csv_content).data
    assert job["valid_rows"] == 1, job
    assert job["error_rows"] == 0
    resp = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert resp.status_code == 200, resp.data
    from inventory.models import SerialNumber, StockBalance

    product = Product.objects.get(company=tenant_a.company, sku="PH-SN2")
    assert product.track_serial is True
    assert StockBalance.objects.get(company=tenant_a.company, product=product).on_hand == Decimal("2")
    numbers = set(
        SerialNumber.objects.filter(company=tenant_a.company, product=product).values_list(
            "serial_number", flat=True
        )
    )
    assert numbers == {"IMEI-1", "IMEI-2"}


def test_fuzzy_headers_product_name_and_item_code(tenant_a):
    csv_content = (
        b"Product Name,Item Code,GST Rate,Selling Price,HSN Code\n"
        b"Soap Bar,SOAP-FZ,18,45,3401\n"
    )
    job = _upload(tenant_a, "products", csv_content).data
    assert job["valid_rows"] == 1
    assert job["error_rows"] == 0
    resp = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert resp.status_code == 200
    assert Product.objects.filter(company=tenant_a.company, sku="SOAP-FZ").exists()


def test_utf8_bom_products_upload(tenant_a):
    csv_content = b"\xef\xbb\xbfname,sku,gst_rate,selling_price\nSoap,SOAP-BOM,18,40\n"
    resp = _upload(tenant_a, "products", csv_content)
    assert resp.status_code == 201, resp.data
    assert resp.data["valid_rows"] == 1


def test_atomic_create_leaves_no_orphan_on_bad_header(tenant_a):
    before_jobs = ImportJob.objects.filter(company=tenant_a.company).count()
    before_files = FileAsset.objects.filter(company=tenant_a.company).count()
    resp = _upload(tenant_a, "customers", b"phone\n9800000001\n")
    assert resp.status_code == 400
    assert ImportJob.objects.filter(company=tenant_a.company).count() == before_jobs
    assert FileAsset.objects.filter(company=tenant_a.company).count() == before_files


def test_master_xlsx_products_import(tenant_a):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["name", "sku", "gst_rate", "selling_price", "hsn_code"])
    ws.append(["Xlsx Soap", "SOAP-XLSX", 18, 55, "3401"])
    buf = BytesIO()
    wb.save(buf)
    content = buf.getvalue()
    resp = _upload(
        tenant_a,
        "products",
        content,
        name="products.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    assert resp.status_code == 201, resp.data
    assert resp.data["valid_rows"] == 1
    commit = tenant_a.client.post(f"/api/v1/imports/{resp.data['id']}/commit/")
    assert commit.status_code == 200
    assert Product.objects.filter(company=tenant_a.company, sku="SOAP-XLSX").exists()


def test_void_opening_stock_import_allows_reimport(tenant_a):
    make_product(tenant_a.company, sku="SKU-VOID")
    csv_content = b"sku,quantity,unit_cost\nSKU-VOID,10,50\n"
    job = _upload(tenant_a, "opening_stock", csv_content).data
    commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert commit.status_code == 200

    void = tenant_a.client.post(f"/api/v1/imports/{job['id']}/void/")
    assert void.status_code == 200, void.data
    assert void.data["status"] == "VOIDED"

    from inventory.models import StockBalance
    bal = StockBalance.objects.get(company=tenant_a.company, product__sku="SKU-VOID")
    assert bal.on_hand == Decimal("0")

    # Re-import same SKU opening stock succeeds.
    job2 = _upload(tenant_a, "opening_stock", csv_content).data
    assert job2["valid_rows"] == 1
    commit2 = tenant_a.client.post(f"/api/v1/imports/{job2['id']}/commit/")
    assert commit2.status_code == 200


def test_void_blocked_after_stock_issued(tenant_a):
    prod = make_product(tenant_a.company, sku="SKU-SOLD")
    csv_content = b"sku,quantity,unit_cost\nSKU-SOLD,10,50\n"
    job = _upload(tenant_a, "opening_stock", csv_content).data
    assert tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/").status_code == 200

    from inventory.models import MovementType
    from inventory.services import InventoryService
    InventoryService.post_movement(
        company=tenant_a.company,
        product=prod,
        movement_type=MovementType.SALE,
        quantity=Decimal("3"),
    )

    void = tenant_a.client.post(f"/api/v1/imports/{job['id']}/void/")
    assert void.status_code == 400


def test_void_products_import_clears_sku_for_reimport(tenant_a):
    csv_content = (
        b"name,sku,gst_rate,selling_price,opening_stock,unit_cost\n"
        b"Void Soap,SOAP-VOID,18,40,5,20\n"
    )
    job = _upload(tenant_a, "products", csv_content).data
    assert tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/").status_code == 200
    assert Product.objects.filter(company=tenant_a.company, sku="SOAP-VOID").exists()

    void = tenant_a.client.post(f"/api/v1/imports/{job['id']}/void/")
    assert void.status_code == 200, void.data

    # SKU freed (cleared or deleted) — re-import works.
    job2 = _upload(tenant_a, "products", csv_content).data
    assert job2["valid_rows"] == 1
    assert tenant_a.client.post(f"/api/v1/imports/{job2['id']}/commit/").status_code == 200


def test_export_inventory_summary_sanitizes_formula_names(tenant_a):
    make_product(tenant_a.company, name="=CMD|calc", sku="EVIL-1")
    from inventory.models import MovementType
    from inventory.services import InventoryService
    InventoryService.post_movement(
        company=tenant_a.company,
        product=Product.objects.get(company=tenant_a.company, sku="EVIL-1"),
        movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("1"),
        unit_cost=Decimal("10"),
    )
    resp = tenant_a.client.get("/api/v1/exports/inventory-summary/")
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    assert "'=CMD|calc" in body


def test_column_mappings_surfaced_for_fuzzy_headers(tenant_a):
    csv_content = (
        b"Product Name,Item Code,GST Rate,Selling Price,HSN Code\n"
        b"Soap Bar,SOAP-MAP,18,45,3401\n"
    )
    job = _upload(tenant_a, "products", csv_content).data
    mappings = {m["source"]: m["target"] for m in job["column_mappings"]}
    assert mappings["product name"] == "name"
    assert mappings["item code"] == "sku"


def test_preview_and_errors_capped_in_response(tenant_a):
    lines = ["name,phone"]
    for i in range(60):
        lines.append(f"Cust {i},9800000{i:03d}")
    # 5 invalid rows (blank name)
    for _ in range(5):
        lines.append(",9800000999")
    content = ("\n".join(lines) + "\n").encode("utf-8")
    job = _upload(tenant_a, "customers", content).data
    assert job["valid_rows"] == 60
    assert job["error_rows"] == 5
    assert len(job["preview"]) == 50
    assert job["preview_truncated"] == 10
    csv_resp = tenant_a.client.get(f"/api/v1/imports/{job['id']}/errors/?as=csv")
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp["Content-Type"]
    commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert commit.status_code == 200
    assert commit.data["created"] == 60
    assert Customer.objects.filter(company=tenant_a.company).count() == 60


def test_void_single_row_when_other_sku_sold(tenant_a):
    make_product(tenant_a.company, sku="SKU-KEEP")
    make_product(tenant_a.company, sku="SKU-VOID-ONE")
    csv_content = b"sku,quantity,unit_cost\nSKU-KEEP,10,50\nSKU-VOID-ONE,10,50\n"
    job = _upload(tenant_a, "opening_stock", csv_content).data
    assert tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/").status_code == 200

    from inventory.models import MovementType, StockBalance
    from inventory.services import InventoryService

    InventoryService.post_movement(
        company=tenant_a.company,
        product=Product.objects.get(company=tenant_a.company, sku="SKU-KEEP"),
        movement_type=MovementType.SALE,
        quantity=Decimal("3"),
    )
    full = tenant_a.client.post(f"/api/v1/imports/{job['id']}/void/")
    assert full.status_code == 400

    row = tenant_a.client.post(
        f"/api/v1/imports/{job['id']}/void-rows/",
        {"skus": ["SKU-VOID-ONE"]},
        format="json",
    )
    assert row.status_code == 200, row.data
    assert row.data["status"] == "COMMITTED"
    bal = StockBalance.objects.get(company=tenant_a.company, product__sku="SKU-VOID-ONE")
    assert bal.on_hand == Decimal("0")
    kept = StockBalance.objects.get(company=tenant_a.company, product__sku="SKU-KEEP")
    assert kept.on_hand == Decimal("7")


def test_tally_export_and_tenant_backup_sanitize_formula_names(tenant_a):
    from datetime import date

    from accounts.tenant_backup import _csv_bytes
    from integrations.tally.adapter import build_tally_export_csv
    from masters.models import Customer
    from sales.models import SalesInvoice

    evil = '=HYPERLINK("http://evil","click")'
    cust = Customer.objects.create(company=tenant_a.company, name=evil)
    SalesInvoice.objects.create(
        company=tenant_a.company,
        customer=cust,
        status=SalesInvoice.Status.COMPLETED,
        invoice_date=date.today(),
        taxable_total=Decimal("10"),
        cgst_total=Decimal("0"),
        sgst_total=Decimal("0"),
        igst_total=Decimal("0"),
        grand_total=Decimal("10"),
    )
    csv_out = build_tally_export_csv(tenant_a.company).decode("utf-8")
    assert "'=HYPERLINK" in csv_out
    backup = _csv_bytes([{"name": evil, "sku": "X"}]).decode("utf-8")
    assert "'=HYPERLINK" in backup
