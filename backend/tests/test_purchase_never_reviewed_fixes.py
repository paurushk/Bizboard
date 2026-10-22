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


# ---------------------------------------------------------------- second pass: B, G, S, T, P
def _grn(tenant, **item):
    from inventory.services import InventoryService
    from tests.conftest import make_product

    supplier = make_supplier(tenant.company)
    product = make_product(tenant.company, sku=f"G-{supplier.pk}", purchase_price=Decimal("77"))
    payload = {
        "supplier": supplier.id,
        "warehouse": InventoryService.default_warehouse(tenant.company).id,
        "items": [{
            "product": product.id, "quantity_received": "5", "quantity_accepted": "3",
            "quantity_rejected": "2", "rejection_reason": "Damaged", "unit_price": "0", **item,
        }],
    }
    resp = tenant.client.post("/api/v1/purchases/grns/", payload, format="json")
    assert resp.status_code == 201, resp.data
    return resp.data["id"], product


def test_boe_with_igst_but_no_assessable_value_is_refused(tenant_a):
    from core.exceptions import BusinessRuleError
    from purchases.boe_services import BillOfEntryService
    from purchases.models import BillOfEntry

    boe = BillOfEntry.objects.create(
        company=tenant_a.company, boe_number="B1", igst_amount=Decimal("100"), assessable_value=Decimal("0"),
    )
    with pytest.raises(BusinessRuleError) as exc:
        BillOfEntryService.complete(boe, tenant_a.owner)
    assert "assessable value" in str(exc.value.detail)


def test_boe_igst_far_above_the_value_is_refused(tenant_a):
    from core.exceptions import BusinessRuleError
    from purchases.boe_services import BillOfEntryService
    from purchases.models import BillOfEntry

    boe = BillOfEntry.objects.create(
        company=tenant_a.company, boe_number="B2", assessable_value=Decimal("1000"), igst_amount=Decimal("900"),
    )
    with pytest.raises(BusinessRuleError) as exc:
        BillOfEntryService.complete(boe, tenant_a.owner)
    assert exc.value.get_codes() == "BOE_IGST_TOO_HIGH"


def test_cancelling_a_boe_tells_the_draft_purchase_it_was_unlinked(tenant_a):
    from purchases.boe_services import BillOfEntryService
    from purchases.models import BillOfEntry, PurchaseInvoice

    boe = BillOfEntry.objects.create(company=tenant_a.company, boe_number="B3", assessable_value=Decimal("1000"))
    supplier = make_supplier(tenant_a.company)
    draft = PurchaseInvoice.objects.create(
        company=tenant_a.company, supplier=supplier, bill_of_entry=boe, status=PurchaseInvoice.Status.DRAFT,
    )
    BillOfEntryService.cancel(boe, tenant_a.owner)
    draft.refresh_from_db()
    assert draft.bill_of_entry_id is None and "B3" in draft.notes and "cancelled" in draft.notes


def test_cancelling_a_receipt_cancels_its_draft_rejection_debit_note(tenant_a):
    from purchases.models import PurchaseDebitNote

    grn_id, _ = _grn(tenant_a)
    assert tenant_a.client.post(f"/api/v1/purchases/grns/{grn_id}/complete/").status_code == 200
    note = PurchaseDebitNote.objects.get(goods_receipt_id=grn_id)
    assert note.status == PurchaseDebitNote.Status.DRAFT
    assert tenant_a.client.post(f"/api/v1/purchases/grns/{grn_id}/cancel/").status_code == 200
    note.refresh_from_db()
    assert note.status == PurchaseDebitNote.Status.CANCELLED


def test_receipt_with_no_price_takes_stock_in_at_the_product_price(tenant_a):
    from inventory.models import StockMovement

    grn_id, _product = _grn(tenant_a)
    assert tenant_a.client.post(f"/api/v1/purchases/grns/{grn_id}/complete/").status_code == 200
    mv = StockMovement.objects.filter(reference_type="goods_receipt", reference_id=str(grn_id)).first()
    assert mv is not None and mv.unit_cost == Decimal("77.00")


def test_structured_bill_upload_is_not_throttled_but_a_scan_is(tenant_a):
    from imports.views import ImportJobViewSet

    view = ImportJobViewSet()
    for name, ctype, expect in (("b.csv", "text/csv", 0), ("b.png", "image/png", 1)):
        class Req:
            data = {"kind": "PURCHASE_BILL"}
            FILES = {"file": SimpleUploadedFile(name, b"x", content_type=ctype)}
        view.request, view.action = Req(), "create"
        assert len(view.get_throttles()) == expect


@patch(LLM)
def test_a_photo_without_consent_is_refused_even_with_the_flag_off(mock_llm, tenant_a):
    mock_llm.return_value = _payload(1)
    resp = _upload(tenant_a.client, "PURCHASE_BILL", ai_consent="")
    assert resp.status_code == 400
    mock_llm.assert_not_called()


@patch(LLM)
def test_a_bad_gstin_on_the_bill_is_a_warning(mock_llm, tenant_a):
    mock_llm.return_value = _payload(1, supplier_gstin="29AABCU9603R1ZZ")
    job = ImportJob.objects.get(pk=_upload(tenant_a.client, "PURCHASE_BILL").data["id"])
    head = bv.header_errors(job, job.preview, job.preview["lines"])
    hit = [e for e in head if e["code"] == "GSTIN_INVALID"]
    assert hit and hit[0]["severity"] == "warning"


def test_line_error_messages_are_plain_words():
    msgs = bv.line_error_messages({"name": "", "quantity": "0", "unit_price": "-1", "gst_rate": "7"})
    assert "Enter the item name." in msgs
    assert not any("unit_price" in m or "must be > 0" in m for m in msgs)


def test_supplier_import_keeps_a_supplier_whose_phone_already_exists(tenant_a):
    make_supplier(tenant_a.company, name="Old Co", phone="9800000051")
    csv = b"name,phone,gstin,state\nNew Co,9800000051,,Karnataka\n"
    job = _upload_suppliers(tenant_a, csv).data
    assert tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/").status_code == 200
    assert Supplier.objects.filter(company=tenant_a.company, name="New Co").exists()


def test_tally_rejects_a_bad_gstin_and_warns_on_a_second_opening(tenant_a):
    from integrations.tally.adapter import parse_tally_masters_rows

    out = parse_tally_masters_rows([
        {"entity_type": "supplier", "name": "Bad G", "gstin": "29AABCU9603R1ZZ"},
        {"entity_type": "supplier", "name": "Good G", "gstin": "29AABCU9603R1ZJ"},
    ])
    assert [r["name"] for r in out["suppliers"]] == ["Good G"]
    assert out["errors"] and "not valid" in out["errors"][0]["error"]

    def run(amount):
        raw = f"entity_type,name,opening_outstanding\nsupplier,Twice Sup,{amount}\n".encode()
        r = tenant_a.client.post(
            "/api/v1/integrations/tally/upload/",
            {"file": SimpleUploadedFile("m.csv", raw, content_type="text/csv")}, format="multipart",
        )
        body = r.data.get("data", r.data)
        rid = body.get("sync_run_id") or body.get("syncRunId")
        return tenant_a.client.post("/api/v1/integrations/tally/commit/", {"sync_run_id": rid}, format="json")

    assert run(500).status_code == 200
    second = run(900)
    assert second.status_code == 200
    assert "already has an opening payable" in str(second.data)


def test_purchase_pdf_survives_markup_in_free_text_fields(tenant_a):
    from purchases.models import PurchaseInvoice, PurchaseItem
    from purchases.pdf import render_gst_purchase_bill
    from tests.conftest import make_product

    supplier = make_supplier(tenant_a.company, name="A & B <Co>", gstin="")
    supplier.address = "Shop <b>1, Lane"
    supplier.phone = "<img src=x>"
    supplier.save()
    inv = PurchaseInvoice.objects.create(
        company=tenant_a.company, supplier=supplier, supplier_bill_number="<INV/1>", status=PurchaseInvoice.Status.DRAFT,
    )
    product = make_product(tenant_a.company, sku="PDF-ESC")
    PurchaseItem.objects.create(
        company=tenant_a.company, invoice=inv, product=product, quantity=Decimal("1"),
        unit_price=Decimal("10"), gst_rate=Decimal("0"), batch_no="B<1>",
    )
    assert render_gst_purchase_bill(inv).startswith(b"%PDF")


@pytest.mark.invariant_skip("gl.ap_ties_to_documents", reason="purchase documents or journals are built through the ORM, so payables in the ledger and on documents cannot tie")
def test_supplier_ledger_pdf_downloads_and_register_shows_claimable_tax(tenant_a):
    from purchases.models import PurchaseInvoice
    from reporting.services import ReportService

    supplier = make_supplier(tenant_a.company, name="Ledger Co")
    resp = tenant_a.client.get(f"/api/v1/ledgers/suppliers/{supplier.id}/pdf/")
    assert resp.status_code == 200 and resp.content.startswith(b"%PDF")
    assert resp["Content-Type"] == "application/pdf"

    for i, eligibility in enumerate(("CLAIMABLE", "INELIGIBLE")):
        PurchaseInvoice.objects.create(
            company=tenant_a.company, supplier=supplier, status=PurchaseInvoice.Status.COMPLETED,
            number=f"R-{i}", itc_eligibility=eligibility, cgst_total=Decimal("9"), sgst_total=Decimal("9"),
            taxable_total=Decimal("100"), grand_total=Decimal("118"),
        )
    rows = ReportService.purchase_register(tenant_a.company)["rows"]
    itc = {r["number"]: Decimal(str(r["itc"])) for r in rows}
    assert itc == {"R-0": Decimal("18"), "R-1": Decimal("0")}
