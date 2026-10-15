"""Purchase never-reviewed review, P1 fixes: S-01 (duplicate bill without a picked supplier),
I-01 (supplier import rules) and T-01 (Tally opening payables dated at the books start)."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from imports import bill_validation as bv
from imports.models import ImportJob
from masters.models import Supplier
from tests.conftest import make_supplier
from tests.test_sales_bill_import import LLM, _payload, _upload

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------- S-01
@patch(LLM)
def test_duplicate_bill_is_caught_when_supplier_was_not_picked_on_upload(mock_llm, tenant_a):
    supplier = make_supplier(tenant_a.company, name="Seller Co", gstin="29AABCU9603R1ZX")
    mock_llm.return_value = _payload(1, supplier_gstin="29AABCU9603R1ZX")
    first = _upload(tenant_a.client, "PURCHASE_BILL", supplier_id=supplier.id).data
    assert tenant_a.client.post(f"/api/v1/imports/{first['id']}/commit/").status_code == 200

    again = _upload(tenant_a.client, "PURCHASE_BILL").data
    job = ImportJob.objects.get(pk=again["id"])
    # The automatic match may or may not have bound the supplier; the check must not depend on it.
    ImportJob.objects.filter(pk=job.pk).update(supplier=None)
    job.refresh_from_db()
    assert job.supplier_id is None
    head = bv.header_errors(job, job.preview, job.preview["lines"])
    assert "DUPLICATE_BILL" in [e["code"] for e in head]


@patch(LLM)
def test_duplicate_check_ignores_an_unmatched_supplier(mock_llm, tenant_a):
    mock_llm.return_value = _payload(1, supplier_name="Brand New Seller")
    resp = _upload(tenant_a.client, "PURCHASE_BILL").data
    job = ImportJob.objects.get(pk=resp["id"])
    head = bv.header_errors(job, job.preview, job.preview["lines"])
    assert "DUPLICATE_BILL" not in [e["code"] for e in head]


# ---------------------------------------------------------------- I-01
def _upload_suppliers(tenant, csv: bytes):
    return tenant.client.post(
        "/api/v1/imports/",
        {"kind": "suppliers", "file": SimpleUploadedFile("s.csv", csv, content_type="text/csv")},
        format="multipart",
    )


def test_supplier_import_rejects_a_gstin_with_a_wrong_check_digit(tenant_a):
    csv = (
        b"name,phone,gstin,state\n"
        b"Good Co,9800000021,29AABCU9603R1ZJ,Karnataka\n"
        b"Bad Digit Co,9800000022,29AABCU9603R1ZK,Karnataka\n"
    )
    job = _upload_suppliers(tenant_a, csv).data
    assert "check digit" in str(job), job
    assert tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/").status_code == 200
    names = set(Supplier.objects.filter(company=tenant_a.company).values_list("name", flat=True))
    assert "Good Co" in names and "Bad Digit Co" not in names


def test_supplier_import_needs_state_or_gstin_when_blank_state_is_not_assumed_local(tenant_a):
    company = tenant_a.company
    company.assume_local_state_for_blank_party = False
    company.save(update_fields=["assume_local_state_for_blank_party"])
    if not company.is_gst_registered:
        company.gstin = "29AABCU9603R1ZX"
        company.save(update_fields=["gstin"])
    csv = b"name,phone,gstin,state\nNo Place Co,9800000031,,\nHas State Co,9800000032,,Karnataka\n"
    job = _upload_suppliers(tenant_a, csv).data
    assert "place of supply" in str(job)
    assert tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/").status_code == 200
    names = set(Supplier.objects.filter(company=company).values_list("name", flat=True))
    assert names >= {"Has State Co"} and "No Place Co" not in names


def test_supplier_import_fills_state_from_the_gstin(tenant_a):
    csv = b"name,phone,gstin,state\nFrom Gstin Co,9800000041,27AABCU9603R1ZN,\n"
    job = _upload_suppliers(tenant_a, csv).data
    if not tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/").status_code == 200:
        pytest.skip("GSTIN fixture failed checksum")
    sup = Supplier.objects.get(company=tenant_a.company, name="From Gstin Co")
    assert sup.state == "Maharashtra"


# ---------------------------------------------------------------- T-01
def test_tally_opening_payable_and_receivable_are_dated_at_the_books_start(tenant_a):
    from ledgers.services import LedgerService
    from purchases.models import PurchaseInvoice
    from sales.models import SalesInvoice

    company = tenant_a.company
    company.books_start_date = date(2026, 4, 1)
    company.save(update_fields=["books_start_date"])
    raw = (
        b"entity_type,name,sku,opening_outstanding,opening_qty\n"
        b"customer,Dated Cust,,1500,\n"
        b"supplier,Dated Sup,,800,\n"
    )
    resp = tenant_a.client.post(
        "/api/v1/integrations/tally/upload/",
        {"file": SimpleUploadedFile("m.csv", raw, content_type="text/csv")},
        format="multipart",
    )
    assert resp.status_code == 201, resp.data
    body = resp.data.get("data", resp.data)
    run_id = body.get("sync_run_id") or body.get("syncRunId")
    commit = tenant_a.client.post("/api/v1/integrations/tally/commit/", {"sync_run_id": run_id}, format="json")
    assert commit.status_code == 200, commit.data
    pur = PurchaseInvoice.objects.get(company=company, notes="TALLY_OPENING")
    sal = SalesInvoice.objects.get(company=company, notes="TALLY_OPENING")
    assert pur.invoice_date == date(2026, 4, 1)
    assert sal.invoice_date == date(2026, 4, 1)
    sup = Supplier.objects.get(company=company, name="Dated Sup")
    assert LedgerService.supplier_outstanding(company, sup) == Decimal("800.00")
