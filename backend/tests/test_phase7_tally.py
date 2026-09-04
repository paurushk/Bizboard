import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from integrations.tally.adapter import DISCLAIMER, parse_tally_masters_csv
from masters.models import Customer, Product


@pytest.mark.django_db
def test_parse_tally_golden_fixture():
    from pathlib import Path

    raw = (Path(__file__).parent / "fixtures" / "tally_masters_golden.csv").read_bytes()
    preview = parse_tally_masters_csv(raw)
    assert preview["counts"]["customers"] == 1
    assert preview["counts"]["suppliers"] == 1
    assert preview["counts"]["products"] == 1
    assert preview["counts"]["errors"] == 0
    assert DISCLAIMER in preview["disclaimer"]


@pytest.mark.django_db
def test_tally_upload_commit_export(tenant_a):
    raw = (
        b"entity_type,name,sku,hsn_code,gst_rate,purchase_price,selling_price,opening_qty\n"
        b"customer,Tally Cust,,,,,,\n"
        b"product,Tally Prod,SKU-T1,8471,18,10,20,5\n"
    )
    f = SimpleUploadedFile("masters.csv", raw, content_type="text/csv")
    resp = tenant_a.client.post(
        "/api/v1/integrations/tally/upload/",
        {"file": f},
        format="multipart",
    )
    assert resp.status_code == 201, resp.data
    # Envelope may camelCase
    body = resp.data.get("data", resp.data)
    run_id = body.get("sync_run_id") or body.get("syncRunId")
    assert run_id

    commit = tenant_a.client.post(
        "/api/v1/integrations/tally/commit/",
        {"sync_run_id": run_id},
        format="json",
    )
    assert commit.status_code == 200, commit.data
    assert Customer.objects.filter(company=tenant_a.company, name="Tally Cust").exists()
    assert Product.objects.filter(company=tenant_a.company, sku="SKU-T1").exists()

    export = tenant_a.client.get("/api/v1/integrations/tally/export/")
    assert export.status_code == 200
    assert "text/csv" in export["Content-Type"]


@pytest.mark.django_db
def test_tally_opening_ar_ap_and_error_report(tenant_a):
    from decimal import Decimal

    from ledgers.services import LedgerService
    from masters.models import Supplier
    from purchases.models import PurchaseInvoice
    from sales.models import SalesInvoice

    raw = (
        b"entity_type,name,sku,opening_outstanding,opening_qty\n"
        b"customer,Open Cust,,1500,\n"
        b"supplier,Open Sup,,800,\n"
        b"bogus,Bad Row,,,\n"
    )
    f = SimpleUploadedFile("masters.csv", raw, content_type="text/csv")
    resp = tenant_a.client.post(
        "/api/v1/integrations/tally/upload/",
        {"file": f},
        format="multipart",
    )
    assert resp.status_code == 201, resp.data
    body = resp.data.get("data", resp.data)
    run_id = body.get("sync_run_id") or body.get("syncRunId")
    preview = body.get("preview") or {}
    assert (preview.get("counts") or {}).get("errors", 0) >= 1

    err = tenant_a.client.get(f"/api/v1/integrations/tally/runs/{run_id}/errors/?as=csv")
    assert err.status_code == 200, (err.status_code, getattr(err, "data", None))
    assert b"error" in err.content.lower()

    # Clear errors so commit is allowed (map step can drop error rows)
    mapped = {
        "customers": preview.get("customers") or [],
        "suppliers": preview.get("suppliers") or [],
        "products": [],
        "errors": [],
    }
    save = tenant_a.client.post(
        "/api/v1/integrations/tally/preview/",
        {"sync_run_id": run_id, "preview": mapped},
        format="json",
    )
    assert save.status_code == 200, save.data

    commit = tenant_a.client.post(
        "/api/v1/integrations/tally/commit/",
        {"sync_run_id": run_id},
        format="json",
    )
    assert commit.status_code == 200, commit.data
    assert SalesInvoice.objects.filter(
        company=tenant_a.company, notes="TALLY_OPENING", status=SalesInvoice.Status.COMPLETED,
    ).exists()
    assert PurchaseInvoice.objects.filter(
        company=tenant_a.company, notes="TALLY_OPENING", status=PurchaseInvoice.Status.COMPLETED,
    ).exists()
    cust = Customer.objects.get(company=tenant_a.company, name="Open Cust")
    sup = Supplier.objects.get(company=tenant_a.company, name="Open Sup")
    assert LedgerService.customer_outstanding(tenant_a.company, cust) == Decimal("1500.00")
    assert LedgerService.supplier_outstanding(tenant_a.company, sup) == Decimal("800.00")

    from reporting.services import ReportService

    dash = ReportService.dashboard(tenant_a.company)
    # Opening invoices must not inflate today sales KPI
    assert Decimal(str(dash["sales_today"]["total"] or 0)) == Decimal("0")


@pytest.mark.django_db
def test_tally_commit_blocked_with_errors(tenant_a):
    raw = b"entity_type,name\nbogus,Bad\n"
    f = SimpleUploadedFile("masters.csv", raw, content_type="text/csv")
    resp = tenant_a.client.post("/api/v1/integrations/tally/upload/", {"file": f}, format="multipart")
    body = resp.data.get("data", resp.data)
    run_id = body.get("sync_run_id") or body.get("syncRunId")
    bad = tenant_a.client.post(
        "/api/v1/integrations/tally/commit/",
        {"sync_run_id": run_id},
        format="json",
    )
    assert bad.status_code == 400


@pytest.mark.django_db
def test_tally_xlsx_parse():

    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["entity_type", "name", "sku"])
    ws.append(["customer", "Xlsx Cust", ""])
    ws.append(["product", "Xlsx Prod", "SKU-X1"])
    buf = io.BytesIO()
    wb.save(buf)
    preview = parse_tally_masters_csv(buf.getvalue(), filename="masters.xlsx")
    assert preview["counts"]["customers"] == 1
    assert preview["counts"]["products"] == 1
    assert preview["counts"]["errors"] == 0


@pytest.mark.django_db
def test_tally_tenant_isolation(tenant_a, tenant_b):
    raw = b"entity_type,name\ncustomer,Only A\n"
    f = SimpleUploadedFile("a.csv", raw, content_type="text/csv")
    resp = tenant_a.client.post("/api/v1/integrations/tally/upload/", {"file": f}, format="multipart")
    body = resp.data.get("data", resp.data)
    run_id = body.get("sync_run_id") or body.get("syncRunId")
    # Tenant B cannot commit A's run
    bad = tenant_b.client.post(
        "/api/v1/integrations/tally/commit/",
        {"sync_run_id": run_id},
        format="json",
    )
    assert bad.status_code in (403, 404)


@pytest.mark.django_db
def test_parse_tally_masters_rejects_over_row_cap():
    """B9-026: an uncapped import file commits its whole party/product loop
    inside one long-held select_for_update transaction — reject it at parse
    time instead of letting it reach the commit transaction at all."""
    from integrations.tally.adapter import MAX_IMPORT_ROWS, parse_tally_masters_rows
    from core.exceptions import BusinessRuleError

    rows = [{"entity_type": "customer", "name": f"Customer {i}"} for i in range(MAX_IMPORT_ROWS + 1)]
    with pytest.raises(BusinessRuleError):
        parse_tally_masters_rows(rows)


@pytest.mark.django_db
def test_parse_tally_masters_allows_exactly_row_cap():
    from integrations.tally.adapter import MAX_IMPORT_ROWS, parse_tally_masters_rows

    rows = [{"entity_type": "customer", "name": f"Customer {i}"} for i in range(MAX_IMPORT_ROWS)]
    preview = parse_tally_masters_rows(rows)
    assert preview["counts"]["customers"] == MAX_IMPORT_ROWS
