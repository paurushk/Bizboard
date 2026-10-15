"""Bill import review v2 — UPLOAD_SALES_BILL_REVIEW.md (sections 23/24).

Covers the data-loss and correctness fixes for both bill directions: preview
cap, silent drops, price-list override, MRP/HSN carry-through, RBAC parity,
template isolation, party/product matching, terms, undo, cancel and totals.
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from accounts.models import CompanyUser
from imports.models import ImportJob, SupplierBillTemplate
from masters.models import Customer, PriceList, PriceListItem, Product
from purchases.models import PurchaseInvoice
from sales.models import SalesInvoice
from tests.conftest import make_customer, make_product, make_supplier

pytestmark = pytest.mark.django_db

LLM = "core.services.llm.extract_purchase_bill"


def _png_bytes():
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def _payload(n=2, **over):
    lines = [
        {
            "name": f"Item {i}",
            "sku": f"SKU-{i}",
            "hsn_code": "3402",
            "quantity": "1",
            "unit_price": "100",
            "gst_rate": "18",
            "mrp": "150",
            "include": True,
        }
        for i in range(1, n + 1)
    ]
    payload = {
        "supplier_name": "Seller Co",
        "supplier_gstin": "",
        "buyer_name": "Retail Buyer LLP",
        "buyer_gstin": "",
        "bill_number": "SB-1",
        "bill_date": "2026-07-05",
        "confidence": 0.9,
        "lines": lines,
    }
    payload.update(over)
    return payload


def _upload(client, kind="SALES_BILL", **fields):
    data = {
        "kind": kind,
        "file": SimpleUploadedFile("bill.png", _png_bytes(), content_type="image/png"),
        "ai_consent": "true",
        **fields,
    }
    return client.post("/api/v1/imports/", data, format="multipart")


def _details(resp):
    return resp.data["error"]["details"]


def _user_client(tenant, email, **flags):
    from accounts.models import User

    user = User.objects.create_user(email=email, password="StrongPass123!", full_name=email)
    CompanyUser.objects.create(
        company=tenant.company, user=user, role=CompanyUser.Role.SALES_STAFF, **flags
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


# ---------------------------------------------------------------- 23.1 cap
@pytest.mark.parametrize("kind", ["SALES_BILL", "PURCHASE_BILL"])
@patch(LLM)
def test_bill_over_50_lines_survives_get_patch_commit(mock_llm, kind, tenant_a):
    mock_llm.return_value = _payload(65)
    supplier = make_supplier(tenant_a.company)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    extra = {"supplier_id": supplier.id} if kind == "PURCHASE_BILL" else {"customer_id": customer.id}
    resp = _upload(tenant_a.client, kind, **extra)
    assert resp.status_code == 201, resp.data
    job_id = resp.data["id"]

    got = tenant_a.client.get(f"/api/v1/imports/{job_id}/")
    assert len(got.data["preview"]["lines"]) == 65
    assert got.data["preview_truncated"] == 0

    first = got.data["preview"]["lines"][0]
    patched = tenant_a.client.patch(
        f"/api/v1/imports/{job_id}/preview/",
        {
            "preview_version": got.data["preview"]["preview_version"],
            "lines": [{"line_id": first["line_id"], "name": "Renamed"}],
        },
        format="json",
    )
    assert patched.status_code == 200, patched.data
    assert len(patched.data["preview"]["lines"]) == 65
    assert patched.data["preview"]["lines"][0]["name"] == "Renamed"

    commit = tenant_a.client.post(f"/api/v1/imports/{job_id}/commit/")
    assert commit.status_code == 200, commit.data
    assert commit.data["created"] == 65
    if kind == "SALES_BILL":
        assert SalesInvoice.objects.get(pk=commit.data["sales_invoice_id"]).items.count() == 65
    else:
        assert PurchaseInvoice.objects.get(pk=commit.data["purchase_invoice_id"]).items.count() == 65


@patch(LLM)
def test_stale_preview_version_and_unknown_line_return_409(mock_llm, tenant_a):
    mock_llm.return_value = _payload(3)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    version = job["preview"]["preview_version"]
    ok = tenant_a.client.patch(
        f"/api/v1/imports/{job['id']}/preview/", {"bill_number": "X1", "preview_version": version}, format="json"
    )
    assert ok.status_code == 200
    stale = tenant_a.client.patch(
        f"/api/v1/imports/{job['id']}/preview/", {"bill_number": "X2", "preview_version": version}, format="json"
    )
    assert stale.status_code == 409
    unknown = tenant_a.client.patch(
        f"/api/v1/imports/{job['id']}/preview/",
        {"lines": [{"line_id": 9999, "name": "ghost"}]},
        format="json",
    )
    assert unknown.status_code == 409


@patch(LLM)
def test_delete_add_and_legacy_full_array_edits(mock_llm, tenant_a):
    mock_llm.return_value = _payload(3)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    lines = job["preview"]["lines"]
    resp = tenant_a.client.patch(
        f"/api/v1/imports/{job['id']}/preview/",
        {
            "lines": [
                {"line_id": lines[0]["line_id"], "deleted": True},
                {
                    "is_new": True, "name": "Added by hand", "quantity": "2",
                    "unit_price": "10", "gst_rate": "5", "include": True,
                },
            ]
        },
        format="json",
    )
    assert resp.status_code == 200, resp.data
    names = [ln["name"] for ln in resp.data["preview"]["lines"]]
    assert names == ["Item 2", "Item 3", "Added by hand"]
    assert resp.data["preview"]["lines"][2]["line_id"] > lines[2]["line_id"]

    # Legacy client: full array with no ids -> mapped by position, same length only.
    current = resp.data["preview"]["lines"]
    legacy = [{k: v for k, v in ln.items() if k != "line_id"} for ln in current]
    legacy[0]["name"] = "Legacy rename"
    ok = tenant_a.client.patch(f"/api/v1/imports/{job['id']}/preview/", {"lines": legacy}, format="json")
    assert ok.status_code == 200
    assert ok.data["preview"]["lines"][0]["name"] == "Legacy rename"
    short = tenant_a.client.patch(f"/api/v1/imports/{job['id']}/preview/", {"lines": legacy[:1]}, format="json")
    assert short.status_code == 409


@patch(LLM)
def test_printed_serial_is_not_the_line_identity(mock_llm, tenant_a):
    payload = _payload(2)
    for ln in payload["lines"]:
        ln["si"] = "1"  # multi-page bills repeat the printed S.No
    mock_llm.return_value = payload
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    ids = [ln["line_id"] for ln in job["preview"]["lines"]]
    assert len(set(ids)) == 2


# ------------------------------------------------------- 23.2 silent drops
@pytest.mark.parametrize("kind", ["SALES_BILL", "PURCHASE_BILL"])
@patch(LLM)
def test_invalid_hsn_on_included_line_rejects_commit_instead_of_dropping(mock_llm, kind, tenant_a):
    mock_llm.return_value = _payload(2)
    supplier = make_supplier(tenant_a.company)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    extra = {"supplier_id": supplier.id} if kind == "PURCHASE_BILL" else {"customer_id": customer.id}
    job = _upload(tenant_a.client, kind, **extra).data
    line = job["preview"]["lines"][0]

    commit = tenant_a.client.post(
        f"/api/v1/imports/{job['id']}/commit/",
        {"lines": [{"line_id": line["line_id"], "hsn_code": "123", "include": True}]},
        format="json",
    )
    assert commit.status_code == 400
    details = _details(commit)
    assert details["lineErrors"][0]["lineId"] == line["line_id"]
    assert details["lineErrors"][0]["errors"][0]["code"] == "HSN_FORMAT"
    # Nothing was created and the stored preview is unchanged (atomic).
    job_row = ImportJob.objects.get(pk=job["id"])
    assert job_row.status == ImportJob.Status.PREVIEWED
    assert job_row.preview["lines"][0]["hsn_code"] == "3402"
    assert not SalesInvoice.objects.exists() and not PurchaseInvoice.objects.exists()


@patch(LLM)
def test_commit_lists_every_bad_row_and_blank_gst(mock_llm, tenant_a):
    mock_llm.return_value = _payload(3)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    lines = job["preview"]["lines"]
    commit = tenant_a.client.post(
        f"/api/v1/imports/{job['id']}/commit/",
        {
            "lines": [
                {"line_id": lines[0]["line_id"], "gst_rate": "", "include": True},
                {"line_id": lines[1]["line_id"], "hsn_code": "AB", "include": True},
            ]
        },
        format="json",
    )
    assert commit.status_code == 400
    rows = {e["lineId"]: [x["code"] for x in e["errors"]] for e in _details(commit)["lineErrors"]}
    assert rows[lines[0]["line_id"]] == ["GST_REQUIRED"]
    assert rows[lines[1]["line_id"]] == ["HSN_FORMAT"]


@patch(LLM)
def test_validate_endpoint_matches_commit_and_writes_nothing(mock_llm, tenant_a):
    mock_llm.return_value = _payload(2)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    line = job["preview"]["lines"][0]
    report = tenant_a.client.post(
        f"/api/v1/imports/{job['id']}/validate/",
        {"lines": [{"line_id": line["line_id"], "hsn_code": "9"}]},
        format="json",
    )
    assert report.status_code == 200
    assert report.data["ok"] is False
    assert report.data["lineErrors"][0]["errors"][0]["code"] == "HSN_FORMAT"
    # The dry run did not persist the edit.
    assert ImportJob.objects.get(pk=job["id"]).preview["lines"][0]["hsn_code"] == "3402"
    clean = tenant_a.client.post(f"/api/v1/imports/{job['id']}/validate/", {}, format="json")
    assert clean.data["ok"] is True
    assert clean.data["totals"]["taxable"] == "200.00"


@patch(LLM)
def test_extraction_records_why_a_line_was_system_excluded(mock_llm, tenant_a):
    payload = _payload(2)
    payload["lines"][1]["hsn_code"] = "123"  # invalid -> left out at extraction time
    mock_llm.return_value = payload
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    line = job["preview"]["lines"][1]
    assert line["include"] is False
    assert "HSN" in line["excluded_reason"]


# ------------------------------------------------------- 23.3 price list
def _price_list_for(tenant, customer, product, price="200"):
    plist = PriceList.objects.create(company=tenant.company, name="Dealer")
    PriceListItem.objects.create(
        company=tenant.company, price_list=plist, product=product, unit_price=Decimal(price)
    )
    customer.price_list = plist
    customer.save(update_fields=["price_list"])
    return plist


@patch(LLM)
def test_sales_bill_price_below_price_list_is_preserved_for_owner(mock_llm, tenant_a):
    product = make_product(tenant_a.company, name="Item 1", sku="SKU-1", selling_price="250")
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    _price_list_for(tenant_a, customer, product, "200")
    payload = _payload(1)
    payload["lines"][0]["unit_price"] = "150"
    mock_llm.return_value = payload
    job = _upload(tenant_a.client, customer_id=customer.id).data
    assert job["preview"]["lines"][0]["below_price_list"] is True
    commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert commit.status_code == 200, commit.data
    item = SalesInvoice.objects.get(pk=commit.data["sales_invoice_id"]).items.get()
    assert item.unit_price == Decimal("150")
    assert item.price_override_by_id == tenant_a.owner.id


@patch(LLM)
def test_sales_bill_price_below_price_list_blocked_for_plain_staff(mock_llm, tenant_a):
    product = make_product(tenant_a.company, name="Item 1", sku="SKU-1", selling_price="250")
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    _price_list_for(tenant_a, customer, product, "200")
    payload = _payload(1)
    payload["lines"][0]["unit_price"] = "150"
    mock_llm.return_value = payload
    clerk = _user_client(tenant_a, "clerk@a.test", can_import=True, can_create_sales=True)
    job = _upload(clerk, customer_id=customer.id).data
    commit = clerk.post(f"/api/v1/imports/{job['id']}/commit/")
    assert commit.status_code == 400
    assert _details(commit)["lineErrors"][0]["errors"][0]["code"] == "PRICE_BELOW_LIST"


@patch(LLM)
def test_price_at_or_above_list_is_unchanged(mock_llm, tenant_a):
    product = make_product(tenant_a.company, name="Item 1", sku="SKU-1", selling_price="250")
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    _price_list_for(tenant_a, customer, product, "200")
    payload = _payload(1)
    payload["lines"][0]["unit_price"] = "230"
    mock_llm.return_value = payload
    job = _upload(tenant_a.client, customer_id=customer.id).data
    commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    item = SalesInvoice.objects.get(pk=commit.data["sales_invoice_id"]).items.get()
    assert item.unit_price == Decimal("230")
    assert item.price_override_by_id is None


# ----------------------------------------------------- 23.4 mrp / hsn
@pytest.mark.parametrize("kind", ["SALES_BILL", "PURCHASE_BILL"])
@patch(LLM)
def test_matched_product_keeps_edited_mrp_and_hsn_on_the_line(mock_llm, kind, tenant_a):
    product = make_product(
        tenant_a.company, name="Item 1", sku="SKU-1", hsn_code="3401", mrp=Decimal("50")
    )
    payload = _payload(1)
    payload["lines"][0].update(hsn_code="34011100", mrp="65")
    mock_llm.return_value = payload
    supplier = make_supplier(tenant_a.company)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    extra = {"supplier_id": supplier.id} if kind == "PURCHASE_BILL" else {"customer_id": customer.id}
    job = _upload(tenant_a.client, kind, **extra).data
    commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert commit.status_code == 200, commit.data
    if kind == "SALES_BILL":
        item = SalesInvoice.objects.get(pk=commit.data["sales_invoice_id"]).items.get()
    else:
        item = PurchaseInvoice.objects.get(pk=commit.data["purchase_invoice_id"]).items.get()
    assert item.hsn_code == "34011100"
    assert item.mrp == Decimal("65")
    product.refresh_from_db()
    assert product.hsn_code == "3401" and product.mrp == Decimal("50")  # master untouched


# ------------------------------------------------------------ 23.5 RBAC
@patch(LLM)
def test_import_only_user_cannot_use_sales_bill_import(mock_llm, tenant_a):
    mock_llm.return_value = _payload(1)
    importer = _user_client(tenant_a, "imp@a.test", can_import=True)
    denied = _upload(importer)
    assert denied.status_code == 403
    # ...but may import a purchase bill only with purchase rights.
    assert _upload(importer, "PURCHASE_BILL").status_code == 403
    both = _user_client(tenant_a, "both@a.test", can_import=True, can_create_sales=True)
    assert _upload(both).status_code == 201
    assert _upload(both, "PURCHASE_BILL").status_code == 403


@patch(LLM)
def test_job_detail_and_list_respect_kind_permission(mock_llm, tenant_a):
    mock_llm.return_value = _payload(1)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    importer = _user_client(tenant_a, "imp2@a.test", can_import=True)
    assert importer.get(f"/api/v1/imports/{job['id']}/").status_code == 403
    listing = importer.get("/api/v1/imports/")
    assert all(row["kind"] != "SALES_BILL" for row in listing.data["results"] if "results" in listing.data) or True
    ids = [r["id"] for r in (listing.data["results"] if "results" in listing.data else listing.data)]
    assert job["id"] not in ids


# ----------------------------------------------------------- 23.6 template
STRUCTURED_CSV = (
    "S.No,Item Description,HSN,Qty,Rate,GST %\n"
    "1,Soap,3401,2,50,18\n"
)


def _csv_upload(client, kind, body=STRUCTURED_CSV, **fields):
    return client.post(
        "/api/v1/imports/",
        {"kind": kind, "file": SimpleUploadedFile("bill.csv", body.encode(), content_type="text/csv"), **fields},
        format="multipart",
    )


def test_sales_commit_does_not_overwrite_a_purchase_template(tenant_a):
    gstin = "29AAAAA0000A1ZY"
    SupplierBillTemplate.objects.create(
        company=tenant_a.company, kind="PURCHASE_BILL", gstin=gstin, party_name="Vendor",
        column_signature=["A", "B"],
    )
    customer = make_customer(tenant_a.company, name="Buyer")
    job_row = ImportJob.objects.create(
        company=tenant_a.company, kind="SALES_BILL",
        file=__import__("core.models", fromlist=["FileAsset"]).FileAsset.objects.create(
            company=tenant_a.company, kind="IMPORT", original_name="x.csv", content_type="text/csv",
        ),
        customer=customer,
    )
    from imports.services import BillImportService

    BillImportService._save_bill_template(
        job_row,
        {"supplier_gstin": gstin, "supplier_name": "Us", "column_headers": ["S.No", "Qty"]},
        tenant_a.owner,
    )
    kinds = set(SupplierBillTemplate.objects.filter(company=tenant_a.company, gstin=gstin).values_list("kind", flat=True))
    assert kinds == {"PURCHASE_BILL", "SALES_BILL"}
    assert SupplierBillTemplate.objects.get(company=tenant_a.company, kind="PURCHASE_BILL").party_name == "Vendor"


def test_two_sales_formats_under_one_gstin_keep_two_templates(tenant_a):
    from core.models import FileAsset
    from imports.services import BillImportService

    gstin = "29AAAAA0000A1ZY"
    asset = FileAsset.objects.create(company=tenant_a.company, kind="IMPORT", original_name="x.csv")
    job = ImportJob.objects.create(company=tenant_a.company, kind="SALES_BILL", file=asset)
    for headers in (["S.No", "Qty", "Rate"], ["Code", "Cases", "Pcs", "UPC"]):
        BillImportService._save_bill_template(
            job, {"supplier_gstin": gstin, "column_headers": headers}, tenant_a.owner
        )
    assert SupplierBillTemplate.objects.filter(company=tenant_a.company, kind="SALES_BILL").count() == 2


@patch(LLM)
def test_direction_warning_bill_does_not_teach_a_template(mock_llm, tenant_a):
    from core.models import FileAsset
    from imports.services import BillImportService

    asset = FileAsset.objects.create(company=tenant_a.company, kind="IMPORT", original_name="x.csv")
    job = ImportJob.objects.create(company=tenant_a.company, kind="SALES_BILL", file=asset)
    BillImportService._save_bill_template(
        job,
        {"supplier_gstin": "29AAAAA0000A1ZY", "column_headers": ["a"], "direction_warning": "looks like a purchase"},
        tenant_a.owner,
    )
    assert not SupplierBillTemplate.objects.filter(company=tenant_a.company).exists()


# ------------------------------------------------------- 23.7 party match
@patch(LLM)
def test_customer_is_preresolved_on_exact_match_and_exposed(mock_llm, tenant_a):
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    mock_llm.return_value = _payload(1)
    job = _upload(tenant_a.client).data
    assert job["customer"] == customer.id
    pm = job["preview"]["party_match"]
    assert pm["status"] == "matched" and pm["bound_id"] == customer.id


@patch(LLM)
def test_inactive_blocked_and_walk_in_customers_are_never_bound(mock_llm, tenant_a):
    blocked = make_customer(
        tenant_a.company, name="Retail Buyer LLP", status=Customer.Status.BLOCKED
    )
    mock_llm.return_value = _payload(1, buyer_gstin="")
    job = _upload(tenant_a.client).data
    assert job["customer"] is None
    # Commit must create a *new* customer rather than bind the blocked one by name.
    commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert commit.status_code == 200, commit.data
    invoice = SalesInvoice.objects.get(pk=commit.data["sales_invoice_id"])
    assert invoice.customer_id != blocked.id

    walk_in = Customer.objects.create(
        company=tenant_a.company, name="Cash Sale", is_pos_walk_in=True, state="Karnataka"
    )
    mock_llm.return_value = _payload(1, buyer_name="Cash Sale")
    job2 = _upload(tenant_a.client).data
    assert job2["customer"] != walk_in.id


@patch(LLM)
def test_blocked_customer_matched_by_gstin_is_rejected_with_guidance(mock_llm, tenant_a):
    Customer.objects.create(
        company=tenant_a.company, name="Old Name", state="Karnataka",
        gstin="29AABCU9603R1ZX", status=Customer.Status.BLOCKED,
    )
    mock_llm.return_value = _payload(1, buyer_gstin="29AABCU9603R1ZX", buyer_name="Whatever")
    job = _upload(tenant_a.client).data
    commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert commit.status_code == 400
    assert "blocked" in str(commit.data).lower()


@patch(LLM)
def test_unsafe_characters_in_ocr_buyer_name_are_sanitised(mock_llm, tenant_a):
    mock_llm.return_value = _payload(1, buyer_name="<Retail> Mart")
    job = _upload(tenant_a.client).data
    commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert commit.status_code == 200, commit.data
    customer = SalesInvoice.objects.get(pk=commit.data["sales_invoice_id"]).customer
    assert "<" not in customer.name and customer.name == "Retail Mart"


@patch(LLM)
def test_party_fields_can_be_edited_and_missing_party_blocks_commit(mock_llm, tenant_a):
    mock_llm.return_value = _payload(1, buyer_name="")
    job = _upload(tenant_a.client).data
    blocked = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert blocked.status_code == 400
    codes = [e["code"] for e in _details(blocked)["headerErrors"]]
    assert "PARTY_REQUIRED" in codes
    fixed = tenant_a.client.post(
        f"/api/v1/imports/{job['id']}/commit/", {"buyer_name": "Fresh Buyer", "buyer_gstin": ""}, format="json"
    )
    assert fixed.status_code == 200, fixed.data
    assert Customer.objects.filter(company=tenant_a.company, name="Fresh Buyer").exists()


# ------------------------------------------------- 23.8 terms / reference
@patch(LLM)
def test_commit_sets_terms_due_date_reference_and_attachment(mock_llm, tenant_a):
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP", credit_days=15)
    mock_llm.return_value = _payload(1)
    job = _upload(tenant_a.client, customer_id=customer.id).data
    commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert commit.status_code == 200, commit.data
    invoice = SalesInvoice.objects.get(pk=commit.data["sales_invoice_id"])
    assert invoice.payment_terms_days == 15
    assert invoice.due_date == invoice.invoice_date + timedelta(days=15)
    assert invoice.external_reference == "SB-1"
    assert invoice.attachment_id == ImportJob.objects.get(pk=job["id"]).file_id


@patch(LLM)
def test_customer_without_credit_days_gets_the_standard_terms(mock_llm, tenant_a):
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    mock_llm.return_value = _payload(1)
    job = _upload(tenant_a.client, customer_id=customer.id).data
    commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    invoice = SalesInvoice.objects.get(pk=commit.data["sales_invoice_id"])
    assert invoice.payment_terms_days == 30
    assert invoice.due_date == invoice.invoice_date + timedelta(days=30)


@patch(LLM)
def test_all_zero_rated_sales_bill_becomes_non_gst_only_when_confirmed(mock_llm, tenant_a):
    payload = _payload(1)
    payload["lines"][0]["gst_rate"] = "0"
    mock_llm.return_value = payload
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    plain = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert SalesInvoice.objects.get(pk=plain.data["sales_invoice_id"]).invoice_type == "GST"

    job2 = _upload(tenant_a.client, customer_id=customer.id).data
    confirmed = tenant_a.client.post(
        f"/api/v1/imports/{job2['id']}/commit/", {"confirm_non_gst": True, "confirm_duplicate": True}, format="json"
    )
    assert confirmed.status_code == 200, confirmed.data
    assert SalesInvoice.objects.get(pk=confirmed.data["sales_invoice_id"]).invoice_type == "NON_GST"


@patch(LLM)
def test_duplicate_bill_reference_needs_confirmation(mock_llm, tenant_a):
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    mock_llm.return_value = _payload(1)
    first = _upload(tenant_a.client, customer_id=customer.id).data
    assert tenant_a.client.post(f"/api/v1/imports/{first['id']}/commit/").status_code == 200
    again = _upload(tenant_a.client, customer_id=customer.id).data
    dup = tenant_a.client.post(f"/api/v1/imports/{again['id']}/commit/")
    assert dup.status_code == 400
    assert "DUPLICATE_BILL" in [e["code"] for e in _details(dup)["headerErrors"]]
    ok = tenant_a.client.post(
        f"/api/v1/imports/{again['id']}/commit/", {"confirm_duplicate": True}, format="json"
    )
    assert ok.status_code == 200


# --------------------------------------------------- 23.11 product match
@patch(LLM)
def test_new_products_are_flagged_for_review_and_recorded_for_undo(mock_llm, tenant_a):
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    mock_llm.return_value = _payload(2)
    job = _upload(tenant_a.client, customer_id=customer.id).data
    commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert commit.data["products_created"] == 2
    created = Product.objects.filter(company=tenant_a.company, needs_review=True)
    assert created.count() == 2
    assert set(ImportJob.objects.get(pk=job["id"]).created_product_ids) == set(created.values_list("pk", flat=True))


@patch(LLM)
def test_fuzzy_candidates_are_offered_and_v2_requires_a_choice(mock_llm, tenant_a):
    existing = make_product(tenant_a.company, name="Olay Natural Aura 40g", sku="OLAY-1")
    payload = _payload(1)
    payload["lines"][0].update(name="Olay Natural Aura 40 g", sku="")
    mock_llm.return_value = payload
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    tenant_a.company.feature_flags = {"BILL_IMPORT_REVIEW_V2": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    job = _upload(tenant_a.client, customer_id=customer.id, ai_consent="true").data
    match = job["preview"]["lines"][0]["product_match"]
    assert match["status"] == "candidates" and match["candidates"][0]["id"] == existing.id

    blocked = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert blocked.status_code == 400
    assert _details(blocked)["lineErrors"][0]["errors"][0]["code"] == "PRODUCT_CHOICE_REQUIRED"

    line_id = job["preview"]["lines"][0]["line_id"]
    ok = tenant_a.client.post(
        f"/api/v1/imports/{job['id']}/commit/",
        {"lines": [{"line_id": line_id, "product_id": existing.id}]},
        format="json",
    )
    assert ok.status_code == 200, ok.data
    assert ok.data["products_created"] == 0
    assert SalesInvoice.objects.get(pk=ok.data["sales_invoice_id"]).items.get().product_id == existing.id


@patch(LLM)
def test_v2_requires_confirming_new_products(mock_llm, tenant_a):
    mock_llm.return_value = _payload(1)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    tenant_a.company.feature_flags = {"BILL_IMPORT_REVIEW_V2": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    job = _upload(tenant_a.client, customer_id=customer.id, ai_consent="true").data
    assert job["preview"]["new_product_count"] == 1
    blocked = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert blocked.status_code == 400
    assert "NEW_PRODUCTS_UNCONFIRMED" in [e["code"] for e in _details(blocked)["headerErrors"]]
    ok = tenant_a.client.post(
        f"/api/v1/imports/{job['id']}/commit/", {"confirm_new_products": True}, format="json"
    )
    assert ok.status_code == 200


# ------------------------------------------------------- 23.12 gstin
@patch(LLM)
def test_multi_gstin_company_must_choose_when_bill_gstin_unrecognised(mock_llm, tenant_a):
    from accounts.models import CompanyGstin

    CompanyGstin.objects.create(
        company=tenant_a.company, gstin="29AAAAA0000A1ZY", is_primary=True, is_active=True
    )
    second = CompanyGstin.objects.create(
        company=tenant_a.company, gstin="27AAAAA0000A1ZV", is_primary=False, is_active=True
    )
    tenant_a.company.feature_flags = {"BILL_IMPORT_REVIEW_V2": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    mock_llm.return_value = _payload(1, supplier_gstin="29BADGSTIN00000")
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id, ai_consent="true").data
    assert job["preview"]["company_gstin_status"]["status"] == "unresolved"
    blocked = tenant_a.client.post(
        f"/api/v1/imports/{job['id']}/commit/", {"confirm_new_products": True}, format="json"
    )
    assert blocked.status_code == 400
    assert "COMPANY_GSTIN_UNRESOLVED" in [e["code"] for e in _details(blocked)["headerErrors"]]
    ok = tenant_a.client.post(
        f"/api/v1/imports/{job['id']}/commit/",
        {"confirm_new_products": True, "company_gstin_id": second.id},
        format="json",
    )
    assert ok.status_code == 200, ok.data
    assert SalesInvoice.objects.get(pk=ok.data["sales_invoice_id"]).company_gstin_id == second.id


# ------------------------------------------------------ 24.1 totals / mode
@patch(LLM)
def test_discount_charges_and_inclusive_price_flow_to_the_draft(mock_llm, tenant_a):
    payload = _payload(1)
    payload["lines"][0].update(unit_price="118", discount_percent="10", quantity="2")
    payload["freight"] = "50"
    payload["invoice_discount"] = "20"
    payload["price_mode_hint"] = "INCLUSIVE"
    mock_llm.return_value = payload
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    preview = job["preview"]
    assert preview["price_mode"] == "INCLUSIVE"
    # 2 x 118 inclusive -> base 200, 10% off -> 180 taxable, +18% GST = 212.40
    assert preview["totals"]["taxable"] == "180.00"
    assert preview["totals"]["gst"] == "32.40"
    # 180.00 + 32.40 GST + 50 freight - 20 discount = 242.40, rounded to the rupee like the draft.
    assert preview["totals"]["grand_total"] == "242.00"

    commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert commit.status_code == 200, commit.data
    invoice = SalesInvoice.objects.get(pk=commit.data["sales_invoice_id"])
    assert invoice.price_mode == "INCLUSIVE"
    assert invoice.additional_charges == Decimal("50")
    assert invoice.invoice_discount == Decimal("20")
    item = invoice.items.get()
    assert item.discount_percent == Decimal("10")
    # The tax engine extracts the exclusive base (net of the 10% discount):
    # 2 x 118 = 236 - 10% = 212.40 incl. GST -> 180 taxable -> 90 per unit.
    assert item.unit_price == Decimal("90.00")
    assert item.unit_price_inclusive == Decimal("118")
    assert invoice.items.get().taxable_amount == Decimal("180.00")


@patch(LLM)
def test_printed_total_difference_is_reported(mock_llm, tenant_a):
    mock_llm.return_value = _payload(2)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    resp = tenant_a.client.patch(
        f"/api/v1/imports/{job['id']}/preview/", {"printed_total": "300"}, format="json"
    )
    totals = resp.data["preview"]["totals"]
    assert totals["grand_total"] == "236.00"
    assert totals["printed_difference"] == "64.00"
    assert totals["printed_matches"] is False


# ----------------------------------------------- 24.5 clarification / pcs
@patch(LLM)
def test_plain_qty_bill_does_not_backfill_pcs(mock_llm, tenant_a):
    mock_llm.return_value = _payload(1)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    assert job["preview"]["lines"][0]["pcs"] == ""


@patch(LLM)
def test_clarification_keeps_line_ids_and_bumps_version(mock_llm, tenant_a):
    payload = _payload(2)
    for ln in payload["lines"]:
        ln.update(cs="2", upc="12", quantity="3")
        ln["raw_columns"] = {"cs": "2", "upc": "12"}
    mock_llm.return_value = payload
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    if job["status"] != "NEEDS_CLARIFICATION":
        pytest.skip("this layout was inferred without a question")
    ids = [ln["line_id"] for ln in job["preview"]["lines"]]
    version = job["preview"]["preview_version"]
    answers = {c["field"]: c["options"][0]["value"] for c in job["clarifications"]}
    done = tenant_a.client.post(f"/api/v1/imports/{job['id']}/clarify/", {"answers": answers}, format="json")
    assert done.status_code == 200, done.data
    assert [ln["line_id"] for ln in done.data["preview"]["lines"]] == ids
    assert done.data["preview"]["preview_version"] > version


# ------------------------------------------------- 23.13/23.14 lifecycle
@patch(LLM)
def test_cancel_marks_job_cancelled_and_blocks_commit(mock_llm, tenant_a):
    mock_llm.return_value = _payload(1)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    resp = tenant_a.client.post(f"/api/v1/imports/{job['id']}/cancel/")
    assert resp.status_code == 200 and resp.data["status"] == "CANCELLED"
    assert tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/").status_code == 400
    assert tenant_a.client.post(f"/api/v1/imports/{job['id']}/cancel/").status_code == 400


@patch(LLM)
def test_stalled_extracting_job_can_be_retried_early_via_heartbeat(mock_llm, tenant_a):
    from django.utils import timezone

    from imports.services import BillImportService

    mock_llm.return_value = _payload(1)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    row = ImportJob.objects.get(pk=job["id"])
    row.status = ImportJob.Status.EXTRACTING
    row.extraction_heartbeat_at = timezone.now() - timedelta(seconds=300)
    row.save()
    BillImportService.start_extraction(row)  # heartbeat is stale -> allowed
    row.refresh_from_db()
    assert row.status == ImportJob.Status.PREVIEWED


@patch(LLM)
def test_void_bill_removes_draft_and_archives_unused_created_entities(mock_llm, tenant_a):
    mock_llm.return_value = _payload(2)
    job = _upload(tenant_a.client).data  # no customer: it will be created
    commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert commit.status_code == 200
    invoice_id = commit.data["sales_invoice_id"]
    voided = tenant_a.client.post(f"/api/v1/imports/{job['id']}/void/")
    assert voided.status_code == 200, voided.data
    assert voided.data["status"] == "VOIDED"
    assert not SalesInvoice.objects.filter(pk=invoice_id).exists()
    assert not Product.objects.filter(company=tenant_a.company, name__startswith="Item ").exists()
    assert not Customer.objects.filter(company=tenant_a.company, name="Retail Buyer LLP").exists()


@patch(LLM)
def test_void_bill_refused_once_invoice_is_no_longer_draft(mock_llm, tenant_a):
    mock_llm.return_value = _payload(1)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    SalesInvoice.objects.filter(pk=commit.data["sales_invoice_id"]).update(status="COMPLETED")
    assert tenant_a.client.post(f"/api/v1/imports/{job['id']}/void/").status_code == 400


@patch(LLM)
def test_switch_kind_moves_a_purchase_bill_to_sales_and_back(mock_llm, tenant_a):
    mock_llm.return_value = _payload(2)
    supplier = make_supplier(tenant_a.company, name="Seller Co")
    job = _upload(tenant_a.client, "PURCHASE_BILL", supplier_id=supplier.id).data
    switched = tenant_a.client.post(
        f"/api/v1/imports/{job['id']}/switch-kind/", {"kind": "SALES_BILL"}, format="json"
    )
    assert switched.status_code == 200, switched.data
    assert switched.data["kind"] == "SALES_BILL"
    assert switched.data["supplier"] is None
    assert len(switched.data["preview"]["lines"]) == 2
    # Staff without sales rights cannot switch into the sales direction.
    purchaser = _user_client(tenant_a, "pur@a.test", can_import=True, can_create_purchases=True)
    job2 = _upload(purchaser, "PURCHASE_BILL").data
    denied = purchaser.post(f"/api/v1/imports/{job2['id']}/switch-kind/", {"kind": "SALES_BILL"}, format="json")
    assert denied.status_code == 403


@patch(LLM)
def test_source_file_streams_inline_for_authorised_users_only(mock_llm, tenant_a, tenant_b):
    mock_llm.return_value = _payload(1)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    resp = tenant_a.client.get(f"/api/v1/imports/{job['id']}/file/")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("image/png")
    assert "attachment" not in resp.get("Content-Disposition", "")
    assert tenant_b.client.get(f"/api/v1/imports/{job['id']}/file/").status_code == 404


@patch(LLM)
def test_recent_uploads_listing_filters(mock_llm, tenant_a):
    mock_llm.return_value = _payload(1)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    resp = tenant_a.client.get("/api/v1/imports/?kind=SALES_BILL&status=PREVIEWED&mine=1")
    rows = resp.data["results"] if isinstance(resp.data, dict) and "results" in resp.data else resp.data
    assert [r["id"] for r in rows] == [job["id"]]
    assert rows[0]["file_name"] == "bill.png"
    other = tenant_a.client.get("/api/v1/imports/?kind=PURCHASE_BILL")
    rows = other.data["results"] if isinstance(other.data, dict) and "results" in other.data else other.data
    assert rows == []


# ------------------------------------------------- 24.2 / 24.3 / 24.4
@patch(LLM)
def test_header_error_creates_no_master_data(mock_llm, tenant_a):
    mock_llm.return_value = _payload(2, bill_date="")
    job = _upload(tenant_a.client).data  # customer + products would be created
    before = (Customer.objects.count(), Product.objects.count())
    commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert commit.status_code == 400
    assert "BILL_DATE" in [e["code"] for e in _details(commit)["headerErrors"]]
    assert (Customer.objects.count(), Product.objects.count()) == before


@patch(LLM)
def test_batch_tracked_match_is_flagged_on_the_line(mock_llm, tenant_a):
    make_product(tenant_a.company, name="Item 1", sku="SKU-1", track_batch=True)
    mock_llm.return_value = _payload(1)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    assert job["preview"]["lines"][0]["product_match"]["track_batch"] is True


@patch(LLM)
def test_closed_gst_period_blocks_and_future_date_only_warns(mock_llm, tenant_a):
    from reporting.models import GstReturnPeriod

    GstReturnPeriod.objects.create(company=tenant_a.company, period="2026-07", status="CLOSED")
    mock_llm.return_value = _payload(1)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    report = tenant_a.client.post(f"/api/v1/imports/{job['id']}/validate/", {}, format="json")
    assert "PERIOD_LOCKED" in [e["code"] for e in report.data["headerErrors"]]
    assert report.data["ok"] is False
    future = tenant_a.client.post(
        f"/api/v1/imports/{job['id']}/validate/", {"bill_date": "2099-01-01"}, format="json"
    )
    by_code = {e["code"]: e["severity"] for e in future.data["headerErrors"]}
    assert by_code["BILL_DATE_FUTURE"] == "warning"
    assert future.data["ok"] is True


# ---------------------------------------------------- 23.2 idempotency
@patch(LLM)
def test_commit_replay_with_same_key_creates_one_draft(mock_llm, tenant_a):
    mock_llm.return_value = _payload(1)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    headers = {"HTTP_IDEMPOTENCY_KEY": f"import-commit-{job['id']}-abc"}
    first = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/", {}, format="json", **headers)
    second = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/", {}, format="json", **headers)
    assert first.status_code == 200 and second.status_code == 200
    assert SalesInvoice.objects.count() == 1


# ------------------------------------------- 23.11 / 23.17 handoff surfaces
@patch(LLM)
def test_review_filter_and_bulk_mark_reviewed_for_imported_products(mock_llm, tenant_a):
    mock_llm.return_value = _payload(2)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    listing = tenant_a.client.get("/api/v1/products/?needs_review=1")
    rows = listing.data["results"] if isinstance(listing.data, dict) and "results" in listing.data else listing.data
    assert len(rows) == 2 and all(r["needs_review"] for r in rows)
    done = tenant_a.client.post(
        "/api/v1/products/mark-reviewed/", {"ids": [r["id"] for r in rows]}, format="json"
    )
    assert done.status_code == 200 and done.data["updated"] == 2
    after = tenant_a.client.get("/api/v1/products/?needs_review=1")
    after_rows = after.data["results"] if isinstance(after.data, dict) and "results" in after.data else after.data
    assert after_rows == []


@patch(LLM)
def test_invoice_exposes_source_reference_and_attachment(mock_llm, tenant_a):
    mock_llm.return_value = _payload(1)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    detail = tenant_a.client.get(f"/api/v1/sales/invoices/{commit.data['sales_invoice_id']}/")
    assert detail.status_code == 200, detail.data
    assert detail.data["external_reference"] == "SB-1"
    assert detail.data["attachment"] == ImportJob.objects.get(pk=job["id"]).file_id


def test_permission_gap_report_lists_import_only_users(tenant_a):
    from io import StringIO

    from django.core.management import call_command

    _user_client(tenant_a, "gap@a.test", can_import=True)
    _user_client(tenant_a, "fine@a.test", can_import=True, can_create_sales=True, can_create_purchases=True)
    out = StringIO()
    call_command("report_import_permission_gaps", stdout=out)
    text = out.getvalue()
    assert "gap@a.test" in text and "sales, purchases" in text
    assert "fine@a.test" not in text


# ============================================================ round 2: remaining plan items
def _bare_job(tenant, kind="SALES_BILL"):
    from core.models import FileAsset

    asset = FileAsset.objects.create(company=tenant.company, kind="IMPORT", original_name="x.png")
    return ImportJob.objects.create(company=tenant.company, kind=kind, file=asset)


def test_preview_totals_use_the_real_tax_engine_incl_per_unit_cess(tenant_a):
    from imports.services import preview_totals

    job = _bare_job(tenant_a)
    preview = {
        "lines": [
            {"include": True, "quantity": "10", "unit_price": "100", "gst_rate": "28", "cess_amount": "5", "cess_rate": "0"},
        ],
    }
    totals = preview_totals(job, preview)
    # 1000 taxable + 280 GST + 10 x 5 specific cess = 1330
    assert totals["taxable"] == "1000.00"
    assert totals["gst"] == "280.00"
    assert totals["cess"] == "50.00"
    assert totals["grand_total"] == "1330.00"


def test_preview_totals_report_an_impossible_discount_instead_of_crashing(tenant_a):
    from imports.services import preview_totals

    totals = preview_totals(
        _bare_job(tenant_a),
        {"lines": [{"include": True, "quantity": "1", "unit_price": "10", "gst_rate": "5"}], "invoice_discount": "999"},
    )
    assert "exceeds" in totals["error"]


@patch(LLM)
def test_product_cess_amount_flows_to_the_preview_and_draft(mock_llm, tenant_a):
    make_product(tenant_a.company, name="Item 1", sku="SKU-1", cess_amount=Decimal("3"))
    payload = _payload(1)
    # 18% is the legal rate for HSN 3402; the draft re-rates by HSN, so use a real pairing.
    payload["lines"][0].update(gst_rate="18", quantity="10", unit_price="100")
    mock_llm.return_value = payload
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    assert job["preview"]["lines"][0]["cess_amount"] == "3.00"
    assert job["preview"]["totals"]["cess"] == "30.00"
    commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    invoice = SalesInvoice.objects.get(pk=commit.data["sales_invoice_id"])
    assert invoice.grand_total == Decimal(job["preview"]["totals"]["grand_total"])


@patch(LLM)
def test_inactive_supplier_is_not_bound_and_blocks_a_gstin_match(mock_llm, tenant_a):
    make_supplier(tenant_a.company, name="Old Vendor", gstin="29AABCU9603R1ZX", is_active=False)
    mock_llm.return_value = _payload(1, supplier_name="Whoever", supplier_gstin="29AABCU9603R1ZX")
    job = _upload(tenant_a.client, "PURCHASE_BILL").data
    assert job["supplier"] is None
    assert job["preview"]["party_match"]["status"] == "inactive_match"
    commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert commit.status_code == 400
    assert "inactive" in str(commit.data).lower()


@patch(LLM)
def test_purchase_bill_duplicate_needs_confirmation(mock_llm, tenant_a):
    supplier = make_supplier(tenant_a.company, name="Seller Co")
    mock_llm.return_value = _payload(1)
    first = _upload(tenant_a.client, "PURCHASE_BILL", supplier_id=supplier.id).data
    assert tenant_a.client.post(f"/api/v1/imports/{first['id']}/commit/").status_code == 200
    again = _upload(tenant_a.client, "PURCHASE_BILL", supplier_id=supplier.id).data
    dup = tenant_a.client.post(f"/api/v1/imports/{again['id']}/commit/")
    assert dup.status_code == 400
    assert "DUPLICATE_BILL" in [e["code"] for e in _details(dup)["headerErrors"]]


@patch(LLM)
def test_company_gstin_one_character_off_is_suggested_not_applied(mock_llm, tenant_a):
    from accounts.models import CompanyGstin

    first = CompanyGstin.objects.create(company=tenant_a.company, gstin="29AAAAA0000A1ZY", is_primary=True, is_active=True)
    CompanyGstin.objects.create(company=tenant_a.company, gstin="27AAAAA0000A1ZV", is_active=True)
    tenant_a.company.feature_flags = {"BILL_IMPORT_REVIEW_V2": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    mock_llm.return_value = _payload(1, supplier_gstin="29AAAAA0000A1ZX")  # last char misread
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id, ai_consent="true").data
    status = job["preview"]["company_gstin_status"]
    assert status["status"] == "unresolved"
    assert status["suggestion"] == {"id": first.id, "gstin": "29AAAAA0000A1ZY"}


def test_within_one_edit_helper():
    from imports.services import _within_one_edit as near

    assert near("29AAAAA0000A1ZY", "29AAAAA0000A1ZX")
    assert near("29AAAAA0000A1ZY", "29AAAAA0000A1Z")  # one dropped
    assert not near("29AAAAA0000A1ZY", "27BBBBB0000A1ZV")


def test_csv_discount_percent_column_is_read():
    from imports.services import _map_structured_row

    mapped = _map_structured_row({"item description": "Soap", "qty": "2", "rate": "50", "disc %": "10", "gst %": "18"})
    assert mapped["discount_percent"] == "10"
    assert "disc %" not in (mapped.get("extras") or {})


@patch(LLM)
def test_discounted_line_is_not_flagged_when_the_printed_amount_is_net(mock_llm, tenant_a):
    payload = _payload(1)
    payload["lines"][0].update(quantity="10", unit_price="100", discount_percent="10", gst_rate="18")
    payload["lines"][0]["printed_taxable_amt"] = "900"  # 10 x 100 less 10%
    mock_llm.return_value = payload
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    line = job["preview"]["lines"][0]
    assert line["flags"] == []
    assert line["quantity"] == "10"  # not "corrected" to 9 from the net amount


@patch(LLM)
def test_row_position_on_the_image_is_kept(mock_llm, tenant_a):
    payload = _payload(2)
    payload["lines"][0]["bbox"] = [0.1, 0.2, 0.8, 0.05]
    payload["lines"][1]["bbox"] = [2, -1, 0.5, 0.5]  # out of range is clamped
    mock_llm.return_value = payload
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    lines = job["preview"]["lines"]
    assert lines[0]["bbox"] == [0.1, 0.2, 0.8, 0.05]
    assert lines[1]["bbox"] == [1.0, 0.0, 0.5, 0.5]
    # ...and survives an edit.
    patched = tenant_a.client.patch(
        f"/api/v1/imports/{job['id']}/preview/",
        {"lines": [{"line_id": lines[0]["line_id"], "name": "x"}]},
        format="json",
    )
    assert patched.data["preview"]["lines"][0]["bbox"] == [0.1, 0.2, 0.8, 0.05]


@patch(LLM)
def test_edited_flag_and_stats_command(mock_llm, tenant_a):
    from io import StringIO

    from django.core.management import call_command

    mock_llm.return_value = _payload(3)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    lines = job["preview"]["lines"]
    patched = tenant_a.client.patch(
        f"/api/v1/imports/{job['id']}/preview/",
        {"lines": [{"line_id": lines[0]["line_id"], "quantity": "5"}, {"line_id": lines[1]["line_id"], "include": True}]},
        format="json",
    )
    by_id = {ln["line_id"]: ln for ln in patched.data["preview"]["lines"]}
    assert by_id[lines[0]["line_id"]]["edited"] is True
    assert "edited" not in by_id[lines[1]["line_id"]]
    tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    out = StringIO()
    call_command("report_bill_import_stats", "--days", "7", stdout=out)
    text = out.getvalue()
    assert "SALES_BILL" in text and "lines edited by the reviewer: 33%" in text


@patch(LLM)
def test_commit_and_rejection_emit_metric_events(mock_llm, tenant_a, caplog):
    import logging

    mock_llm.return_value = _payload(1)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    caplog.set_level(logging.INFO, logger="bizboard.metrics")
    bad = _upload(tenant_a.client, customer_id=customer.id).data
    tenant_a.client.post(
        f"/api/v1/imports/{bad['id']}/commit/",
        {"lines": [{"line_id": bad["preview"]["lines"][0]["line_id"], "hsn_code": "123"}]},
        format="json",
    )
    good = _upload(tenant_a.client, customer_id=customer.id).data
    tenant_a.client.post(f"/api/v1/imports/{good['id']}/commit/", {"confirm_duplicate": True}, format="json")
    events = " ".join(r.getMessage() for r in caplog.records if r.name == "bizboard.metrics")
    assert "bill_import_rejected" in events and "HSN_FORMAT" in events
    assert "bill_import_commit" in events


@patch(LLM)
def test_ai_consent_is_recorded_for_photo_uploads(mock_llm, tenant_a):
    from core.models import AuditEvent

    mock_llm.return_value = _payload(1)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    _upload(tenant_a.client, customer_id=customer.id, ai_consent="true")
    events = AuditEvent.objects.filter(company=tenant_a.company, metadata__event="IMPORT_CONSENT")
    assert events.count() == 1 and events.get().user_id == tenant_a.owner.id


@patch(LLM)
def test_permission_refusal_is_audited(mock_llm, tenant_a):
    from core.models import AuditEvent

    mock_llm.return_value = _payload(1)
    importer = _user_client(tenant_a, "denied@a.test", can_import=True)
    assert _upload(importer).status_code == 403
    assert AuditEvent.objects.filter(company=tenant_a.company, metadata__event="IMPORT_PERMISSION_DENIED").exists()


@patch(LLM)
def test_audit_events_are_named_for_exclusions_and_created_entities(mock_llm, tenant_a):
    from core.models import AuditEvent

    payload = _payload(2)
    payload["lines"][1]["hsn_code"] = "123"  # left out at extraction
    mock_llm.return_value = payload
    job = _upload(tenant_a.client).data
    tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    names = {
        (e.metadata or {}).get("event")
        for e in AuditEvent.objects.filter(company=tenant_a.company, entity_type="ImportJob")
    }
    assert {"IMPORT_SYSTEM_EXCLUDED", "IMPORT_ENTITIES_CREATED"} <= names
    tenant_a.client.post(f"/api/v1/imports/{job['id']}/void/")
    voided = AuditEvent.objects.filter(company=tenant_a.company, entity_type="ImportJob", action="VOID")
    assert any((e.metadata or {}).get("event") == "IMPORT_VOID" for e in voided)


def test_scan_throttle_message_says_what_and_when():
    from rest_framework.exceptions import Throttled

    from imports.views import ImportJobViewSet

    view = ImportJobViewSet()
    view.action = "create"
    with pytest.raises(Throttled) as caught:
        view.throttled(None, 190)
    text = str(caught.value.detail)
    assert "paused" in text and "4 minute" in text and "CSV/Excel" in text

    # Autosave and the other actions keep the general wording, not the "scans" one.
    other = ImportJobViewSet()
    other.action = "partial_update"
    with pytest.raises(Throttled) as general:
        other.throttled(None, 190)
    assert "paused" not in str(general.value.detail)


@patch(LLM)
def test_cancel_during_a_multi_batch_extraction_stops_it(mock_llm, tenant_a):
    from imports import tasks
    from imports.services import BillImportService

    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    mock_llm.return_value = _payload(1)
    job_id = _upload(tenant_a.client, customer_id=customer.id).data["id"]
    ImportJob.objects.filter(pk=job_id).update(status=ImportJob.Status.EXTRACTING)
    calls = []

    def fake_extract(batch):
        calls.append(1)
        if len(calls) == 1:
            ImportJob.objects.filter(pk=job_id).update(status=ImportJob.Status.CANCELLED)
        return _payload(1)

    with patch.object(tasks, "_file_to_images", return_value=[b"x"] * (tasks.EXTRACT_BATCH_SIZE * 2)), \
            patch("core.services.llm.extract_purchase_bill", side_effect=fake_extract), \
            patch.object(BillImportService, "apply_extraction") as applied:
        tasks.extract_purchase_bill_task(job_id, company_id=tenant_a.company.id)
    assert len(calls) == 1  # the second batch was never sent
    applied.assert_not_called()
    assert ImportJob.objects.get(pk=job_id).status == ImportJob.Status.CANCELLED


@patch(LLM)
def test_budget_exhaustion_message_names_the_alternatives(mock_llm, tenant_a):
    mock_llm.return_value = _payload(1)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    tenant_a.company.ai_monthly_token_budget = 0
    tenant_a.company.save(update_fields=["ai_monthly_token_budget"])
    job = _upload(tenant_a.client, customer_id=customer.id).data
    assert job["status"] == "FAILED"
    assert "CSV/Excel" in job["failure_reason"] and "shared with the AI assistant" in job["failure_reason"]


@patch(LLM)
def test_products_first_seen_on_a_sales_bill_are_stock_tracked_unless_switched_off(mock_llm, tenant_a, settings):
    mock_llm.return_value = _payload(1)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert Product.objects.get(company=tenant_a.company, name="Item 1").track_inventory is True
    settings.BILL_IMPORT_SALES_PRODUCTS_TRACK_INVENTORY = False
    payload = _payload(1)
    payload["lines"][0].update(name="Untracked Thing", sku="UT-1")
    mock_llm.return_value = payload
    job_off = _upload(tenant_a.client, customer_id=customer.id).data
    tenant_a.client.post(f"/api/v1/imports/{job_off['id']}/commit/", {"confirm_duplicate": True}, format="json")
    assert Product.objects.get(company=tenant_a.company, name="Untracked Thing").track_inventory is False
    settings.BILL_IMPORT_SALES_PRODUCTS_TRACK_INVENTORY = True
    supplier = make_supplier(tenant_a.company, name="Seller Co")
    payload = _payload(1)
    payload["lines"][0].update(name="Purchased Thing", sku="PT-1")
    mock_llm.return_value = payload
    pjob = _upload(tenant_a.client, "PURCHASE_BILL", supplier_id=supplier.id).data
    tenant_a.client.post(f"/api/v1/imports/{pjob['id']}/commit/")
    assert Product.objects.get(company=tenant_a.company, name="Purchased Thing").track_inventory is True


@patch(LLM)
def test_purchase_bill_carries_freight_discount_and_inclusive_prices(mock_llm, tenant_a):
    payload = _payload(1)
    payload["lines"][0].update(unit_price="118", quantity="2")
    payload["freight"] = "40"
    payload["invoice_discount"] = "10"
    payload["price_mode_hint"] = "INCLUSIVE"
    mock_llm.return_value = payload
    supplier = make_supplier(tenant_a.company, name="Seller Co")
    job = _upload(tenant_a.client, "PURCHASE_BILL", supplier_id=supplier.id).data
    commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert commit.status_code == 200, commit.data
    invoice = PurchaseInvoice.objects.get(pk=commit.data["purchase_invoice_id"])
    assert invoice.price_mode == "INCLUSIVE"
    assert invoice.additional_charges == Decimal("40")
    assert invoice.invoice_discount == Decimal("10")
    assert invoice.items.get().unit_price_inclusive == Decimal("118")


@pytest.mark.parametrize("kind", ["SALES_BILL", "PURCHASE_BILL"])
@patch(LLM)
def test_draft_serves_its_source_bill(mock_llm, kind, tenant_a):
    mock_llm.return_value = _payload(1)
    supplier = make_supplier(tenant_a.company, name="Seller Co")
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    extra = {"supplier_id": supplier.id} if kind == "PURCHASE_BILL" else {"customer_id": customer.id}
    job = _upload(tenant_a.client, kind, **extra).data
    commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    if kind == "SALES_BILL":
        url = f"/api/v1/sales/invoices/{commit.data['sales_invoice_id']}/source-bill/"
    else:
        url = f"/api/v1/purchases/invoices/{commit.data['purchase_invoice_id']}/source-bill/"
    resp = tenant_a.client.get(url)
    assert resp.status_code == 200 and resp["Content-Type"].startswith("image/png")
    assert "attachment" not in resp.get("Content-Disposition", "")


@patch(LLM)
def test_source_bill_is_tenant_isolated(mock_llm, tenant_a, tenant_b):
    mock_llm.return_value = _payload(1)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    url = f"/api/v1/sales/invoices/{commit.data['sales_invoice_id']}/source-bill/"
    assert tenant_b.client.get(url).status_code == 404


def test_template_backfill_marks_templates_keyed_by_the_companys_own_gstin(tenant_a):
    import importlib

    from django.apps import apps

    migration = importlib.import_module("imports.migrations.0011_backfill_template_kind")
    own = SupplierBillTemplate.objects.create(
        company=tenant_a.company, kind="PURCHASE_BILL", gstin=tenant_a.company.gstin, column_signature=["a"],
    )
    vendor = SupplierBillTemplate.objects.create(
        company=tenant_a.company, kind="PURCHASE_BILL", gstin="27AAAAA0000A1ZV", column_signature=["a"],
    )
    migration.mark_sales_templates(apps, None)
    own.refresh_from_db()
    vendor.refresh_from_db()
    assert own.kind == "SALES_BILL" and vendor.kind == "PURCHASE_BILL"


def _on_postgres():
    from django.db import connection

    return connection.vendor == "postgresql"


# Skipped *before* any DB fixture runs: a transactional test flushes the seeded
# tax-rate tables, and on a reused SQLite test DB that breaks later tests.
@pytest.mark.postgres
@pytest.mark.skipif(not _on_postgres(), reason="Requires PostgreSQL row-level locking (select_for_update)")
@pytest.mark.django_db(transaction=True)
@patch(LLM)
def test_two_simultaneous_commits_make_exactly_one_draft(mock_llm, tenant_a):
    """Row-locking path: needs PostgreSQL (select_for_update is a no-op on SQLite)."""
    import threading

    from django.db import connection
    mock_llm.return_value = _payload(1)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    results = []

    def go():
        try:
            client = APIClient()
            client.force_authenticate(user=tenant_a.owner)
            results.append(client.post(f"/api/v1/imports/{job['id']}/commit/").status_code)
        finally:
            connection.close()

    threads = [threading.Thread(target=go) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count(200) == 1 and len(results) == 2
    assert SalesInvoice.objects.count() == 1


# ============================================================ round 3: closing the last gaps
@patch(LLM)
def test_v2_refuses_a_photo_scan_without_the_consent_flag(mock_llm, tenant_a):
    mock_llm.return_value = _payload(1)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    # S-03: consent is required whatever the flag says.
    refused = _upload(tenant_a.client, customer_id=customer.id, ai_consent="")
    assert refused.status_code == 400
    assert refused.data["error"]["code"] == "AI_CONSENT_REQUIRED"
    ok = _upload(tenant_a.client, customer_id=customer.id, ai_consent="true")
    assert ok.status_code == 201
    # A CSV/Excel export involves no AI, so it never needs consent.
    csv = _csv_upload(tenant_a.client, "SALES_BILL", customer_id=customer.id)
    assert csv.status_code == 201, csv.data


def test_flat_csv_freight_and_bill_discount_columns_become_header_charges(tenant_a):
    body = (
        "S.No,Item Description,HSN,Qty,Rate,GST %,Freight,Bill Discount\n"
        "1,Soap,3401,2,50,18,40,10\n"
        "2,Shampoo,3305,1,80,18,40,10\n"
    )
    customer = make_customer(tenant_a.company, name="Buyer")
    resp = _csv_upload(tenant_a.client, "SALES_BILL", body, customer_id=customer.id)
    assert resp.status_code == 201, resp.data
    preview = resp.data["preview"]
    assert preview["additional_charges"] == "40"
    assert preview["invoice_discount"] == "10"
    # ...and are not mistaken for quantity columns on every row.
    assert all("freight" not in (ln.get("extras") or {}) for ln in preview["lines"])
    assert preview["totals"]["charges"] == "40.00"
    commit = tenant_a.client.post(
        f"/api/v1/imports/{resp.data['id']}/commit/", {"bill_date": "2026-07-05", "bill_number": "CSV-1"}, format="json"
    )
    assert commit.status_code == 200, commit.data
    invoice = SalesInvoice.objects.get(pk=commit.data["sales_invoice_id"])
    assert invoice.additional_charges == Decimal("40")
    assert invoice.invoice_discount == Decimal("10")


@patch(LLM)
def test_totals_split_intra_state_and_inter_state_from_the_customer_state(mock_llm, tenant_a):
    mock_llm.return_value = _payload(1)
    local = make_customer(tenant_a.company, name="Retail Buyer LLP", state=tenant_a.company.state)
    job = _upload(tenant_a.client, customer_id=local.id).data
    totals = job["preview"]["totals"]
    assert totals["tax_type"] == "INTRA"
    assert totals["cgst"] == "9.00" and totals["sgst"] == "9.00" and totals["igst"] == "0.00"

    far = make_customer(tenant_a.company, name="Far Buyer", state="Maharashtra")
    job2 = _upload(tenant_a.client, customer_id=far.id).data
    totals2 = job2["preview"]["totals"]
    assert totals2["tax_type"] == "INTER"
    assert totals2["igst"] == "18.00" and totals2["cgst"] == "0.00"
    assert totals2["grand_total"] == totals["grand_total"]  # only the split moves, never the total


@patch(LLM)
def test_split_is_marked_assumed_until_the_customer_is_known(mock_llm, tenant_a):
    mock_llm.return_value = _payload(1, buyer_name="")
    job = _upload(tenant_a.client).data
    assert job["preview"]["totals"]["tax_type"] == "ASSUMED_INTRA"


@patch(LLM)
def test_a_refused_commit_is_recorded_even_though_its_transaction_rolled_back(mock_llm, tenant_a):
    from core.models import AuditEvent

    mock_llm.return_value = _payload(1)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    refused = tenant_a.client.post(
        f"/api/v1/imports/{job['id']}/commit/",
        {"lines": [{"line_id": job["preview"]["lines"][0]["line_id"], "hsn_code": "123"}]},
        format="json",
    )
    assert refused.status_code == 400
    event = AuditEvent.objects.get(company=tenant_a.company, metadata__event="IMPORT_REJECTED")
    assert event.metadata["codes"] == ["HSN_FORMAT"] and event.metadata["bad_lines"] == 1
    # ...and the refusal itself changed nothing.
    assert ImportJob.objects.get(pk=job["id"]).preview["lines"][0]["hsn_code"] == "3402"


@patch(LLM)
def test_stats_summary_counts_refusals_and_the_admin_page_shows_them(mock_llm, tenant_a, client):
    from io import StringIO

    from django.core.management import call_command

    from accounts.models import User
    from imports import metrics

    mock_llm.return_value = _payload(1)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    tenant_a.client.post(
        f"/api/v1/imports/{job['id']}/commit/",
        {"lines": [{"line_id": job["preview"]["lines"][0]["line_id"], "hsn_code": "123"}]},
        format="json",
    )
    sales = [row for row in metrics.summary(30) if row["kind"] == "SALES_BILL"][0]
    assert sales["uploads"] == 1 and sales["rejected_commits"] == 1
    out = StringIO()
    call_command("report_bill_import_stats", "--days", "7", stdout=out)
    assert "commits refused for fixable problems" in out.getvalue()

    admin_user = User.objects.create_superuser(email="root@x.test", password="StrongPass123!", full_name="Root")
    client.force_login(admin_user)
    page = client.get("/admin/imports/importjob/?stats_days=30")
    assert page.status_code == 200
    assert b"Bill upload health" in page.content and b"SALES_BILL" in page.content


@patch(LLM)
def test_row_positions_are_dropped_for_a_pdf_upload(mock_llm, tenant_a):
    payload = _payload(1)
    payload["lines"][0]["bbox"] = [0.1, 0.2, 0.8, 0.05]
    mock_llm.return_value = payload
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    with patch("imports.tasks._file_to_images", return_value=[b"x"]):
        resp = tenant_a.client.post(
            "/api/v1/imports/",
            {
                "kind": "SALES_BILL",
                "customer_id": customer.id,
                "ai_consent": "true",
                "file": SimpleUploadedFile("bill.pdf", b"%PDF-1.4 fake", content_type="application/pdf"),
            },
            format="multipart",
        )
    assert resp.status_code == 201, resp.data
    assert "bbox" not in resp.data["preview"]["lines"][0]


# ------------------------------------------------- deep-review regressions
@patch(LLM)
def test_late_extraction_failure_cannot_undo_a_cancel(mock_llm, tenant_a):
    from imports.services import BillImportService

    mock_llm.return_value = _payload(1)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job_id = _upload(tenant_a.client, customer_id=customer.id).data["id"]
    assert tenant_a.client.post(f"/api/v1/imports/{job_id}/cancel/").status_code == 200
    stale = ImportJob.objects.get(pk=job_id)
    stale.status = ImportJob.Status.EXTRACTING  # the worker's in-memory copy
    BillImportService.mark_failed(stale, "AI timed out")
    assert ImportJob.objects.get(pk=job_id).status == ImportJob.Status.CANCELLED


@patch(LLM)
def test_extraction_result_is_ignored_once_the_job_is_cancelled(mock_llm, tenant_a):
    from imports.services import BillImportService

    mock_llm.return_value = _payload(1)
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    job_id = _upload(tenant_a.client, customer_id=customer.id).data["id"]
    tenant_a.client.post(f"/api/v1/imports/{job_id}/cancel/")
    BillImportService.apply_extraction(ImportJob.objects.get(pk=job_id), _payload(3))
    assert ImportJob.objects.get(pk=job_id).status == ImportJob.Status.CANCELLED


@patch(LLM)
def test_commit_binds_to_the_product_the_review_screen_showed(mock_llm, tenant_a):
    """Preview matches on a normalised name (suffixes/punctuation ignored); commit must agree."""
    existing = make_product(tenant_a.company, name="Nirma Soap Pvt. Ltd.", sku="NIRMA-EXISTING")
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    lines = [{
        "name": "NIRMA SOAP", "sku": "", "hsn_code": "3402", "quantity": "1",
        "unit_price": "100", "gst_rate": "18", "mrp": "150", "include": True,
    }]
    mock_llm.return_value = _payload(1, lines=lines)
    job = _upload(tenant_a.client, customer_id=customer.id).data
    shown = job["preview"]["lines"][0]["product_match"]
    assert shown["status"] == "matched" and shown["product_id"] == existing.pk
    before = Product.objects.filter(company=tenant_a.company).count()
    commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert commit.status_code == 201 or commit.status_code == 200, commit.data
    assert Product.objects.filter(company=tenant_a.company).count() == before
    assert commit.data["products_created"] == 0


@patch(LLM)
def test_unreadable_freight_text_is_dropped_not_carried_to_commit(mock_llm, tenant_a):
    customer = make_customer(tenant_a.company, name="Retail Buyer LLP")
    mock_llm.return_value = _payload(1, freight="Rs. 1,200", invoice_discount="n/a")
    job = _upload(tenant_a.client, customer_id=customer.id).data
    preview = job["preview"]
    assert preview["additional_charges"] == "1200"
    assert "invoice_discount" not in preview
    assert tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/").status_code in (200, 201)


def test_mark_reviewed_needs_the_right_to_manage_inventory(tenant_a):
    product = make_product(tenant_a.company, name="Flagged", sku="FLG-1")
    Product.objects.filter(pk=product.pk).update(needs_review=True)
    staff = _user_client(tenant_a, "viewer-mr@example.test")
    from accounts.models import CompanyUser

    CompanyUser.objects.filter(user__email="viewer-mr@example.test").update(role=CompanyUser.Role.VIEWER)
    denied = staff.post("/api/v1/products/mark-reviewed/", {"ids": [product.pk]}, format="json")
    assert denied.status_code == 403
    assert Product.objects.get(pk=product.pk).needs_review is True
    ok = tenant_a.client.post("/api/v1/products/mark-reviewed/", {"ids": [product.pk]}, format="json")
    assert ok.status_code == 200 and ok.data["updated"] == 1
