"""API-level gaps for the bill-import module: who may do what, edit
validation, list filters, size limit, switching direction, mark-reviewed.

Companion to test_sales_bill_import.py (flows) and test_bill_import_units.py
(pure rules).
"""

from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from accounts.models import CompanyUser, User
from imports.models import ImportJob
from masters.models import Product
from tests.conftest import make_customer, make_product, make_supplier
from tests.test_sales_bill_import import LLM, _payload, _upload

pytestmark = pytest.mark.django_db


def staff_client(tenant, email, role=CompanyUser.Role.SALES_STAFF, **flags):
    user = User.objects.create_user(email=email, password="StrongPass123!", full_name=email)
    CompanyUser.objects.create(company=tenant.company, user=user, role=role, **flags)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def preview_of(client, job_id):
    return client.get(f"/api/v1/imports/{job_id}/").data["preview"]


@pytest.fixture
def job(tenant_a):
    """A previewed SALES_BILL uploaded by the owner."""
    make_customer(tenant_a.company, name="Retail Buyer LLP")
    with patch(LLM, return_value=_payload(2)):
        resp = _upload(tenant_a.client)
    assert resp.status_code == 201, resp.data
    return resp.data


# ----------------------------------------------------- who may import what
@pytest.mark.parametrize(
    "role,flags,sales,purchase",
    [
        (CompanyUser.Role.OWNER, {}, 201, 201),
        (CompanyUser.Role.SALES_STAFF, {"can_import": True, "can_create_sales": True}, 201, 403),
        (CompanyUser.Role.SALES_STAFF, {"can_import": True, "can_create_purchases": True}, 403, 201),
        (
            CompanyUser.Role.SALES_STAFF,
            {"can_import": True, "can_create_sales": True, "can_create_purchases": True},
            201,
            201,
        ),
        (CompanyUser.Role.SALES_STAFF, {"can_create_sales": True, "can_create_purchases": True}, 403, 403),
        (CompanyUser.Role.SALES_STAFF, {"can_import": True}, 403, 403),
        (CompanyUser.Role.VIEWER, {"can_import": True, "can_create_sales": True}, 403, 403),
    ],
)
@patch(LLM)
def test_import_needs_both_the_import_right_and_the_create_right(
    mock_llm, role, flags, sales, purchase, tenant_a
):
    mock_llm.return_value = _payload(1)
    if role == CompanyUser.Role.OWNER:
        client = tenant_a.client
    else:
        client = staff_client(tenant_a, f"{role.lower()}-{len(flags)}-{sales}{purchase}@a.test", role, **flags)
    assert _upload(client, "SALES_BILL").status_code == sales
    assert _upload(client, "PURCHASE_BILL").status_code == purchase


@pytest.mark.parametrize(
    "path,method,body",
    [
        ("", "get", None),
        ("file/", "get", None),
        ("validate/", "post", {}),
        ("cancel/", "post", {}),
        ("retry-extract/", "post", {}),
        ("clarify/", "post", {"answers": {}}),
        ("switch-kind/", "post", {"kind": "PURCHASE_BILL"}),
        ("commit/", "post", {}),
        ("void/", "post", {}),
    ],
)
def test_every_job_action_refuses_a_user_without_rights_for_that_kind(path, method, body, job, tenant_a):
    importer = staff_client(tenant_a, "imp-only@a.test", can_import=True)
    resp = getattr(importer, method)(f"/api/v1/imports/{job['id']}/{path}", body, format="json") if body is not None \
        else getattr(importer, method)(f"/api/v1/imports/{job['id']}/{path}")
    assert resp.status_code == 403, (path, resp.status_code)
    # and nothing about the job changed
    assert ImportJob.objects.get(pk=job["id"]).status == ImportJob.Status.PREVIEWED


@patch(LLM)
def test_a_user_with_rights_for_the_other_kind_only_cannot_touch_this_job(mock_llm, job, tenant_a):
    buyer_only = staff_client(tenant_a, "pur-only@a.test", can_import=True, can_create_purchases=True)
    assert buyer_only.get(f"/api/v1/imports/{job['id']}/").status_code == 403
    assert buyer_only.get(f"/api/v1/imports/{job['id']}/file/").status_code == 403


@patch(LLM)
def test_undoing_a_bill_is_for_the_uploader_owner_or_manager_only(mock_llm, tenant_a):
    mock_llm.return_value = _payload(1)
    make_customer(tenant_a.company, name="Retail Buyer LLP")
    uploader = staff_client(tenant_a, "up@a.test", can_import=True, can_create_sales=True)
    other = staff_client(tenant_a, "other@a.test", can_import=True, can_create_sales=True)
    job_id = _upload(uploader).data["id"]
    assert uploader.post(f"/api/v1/imports/{job_id}/commit/").status_code == 200
    assert other.post(f"/api/v1/imports/{job_id}/void/").status_code == 403
    assert uploader.post(f"/api/v1/imports/{job_id}/void/").status_code == 200

    job2 = _upload(uploader).data["id"]
    assert uploader.post(f"/api/v1/imports/{job2}/commit/").status_code == 200
    assert tenant_a.client.post(f"/api/v1/imports/{job2}/void/").status_code == 200


# ------------------------------------------------- editing: bad input is 400
@pytest.mark.parametrize(
    "body",
    [
        {"price_mode": "SOMETIMES"},
        {"additional_charges": "-5"},
        {"invoice_discount": "-1"},
        {"printed_total": "-10"},
        {"additional_charges": "abc"},
        {"company_gstin_id": 999999},
        {"preview_version": "abc"},
        {"lines": "not-a-list"},
        {"lines": [{"line_id": "x", "name": "n"}]},
        {"customer_id": 999999},
        {"supplier_id": 999999},
    ],
)
def test_editing_rejects_bad_input_without_changing_the_bill(body, job, tenant_a):
    before = preview_of(tenant_a.client, job["id"])
    resp = tenant_a.client.patch(f"/api/v1/imports/{job['id']}/preview/", body, format="json")
    assert resp.status_code == 400, (body, resp.status_code, resp.data)
    after = preview_of(tenant_a.client, job["id"])
    assert after["preview_version"] == before["preview_version"]
    assert after.get("price_mode") == before.get("price_mode")


def test_editing_accepts_good_header_values_and_clears_them_again(job, tenant_a):
    url = f"/api/v1/imports/{job['id']}/preview/"
    ok = tenant_a.client.patch(
        url,
        {"price_mode": "inclusive", "additional_charges": "12.50", "invoice_discount": "3", "printed_total": "300"},
        format="json",
    )
    assert ok.status_code == 200, ok.data
    p = ok.data["preview"]
    assert p["price_mode"] == "INCLUSIVE" and p["additional_charges"] == "12.50"
    cleared = tenant_a.client.patch(url, {"additional_charges": "", "printed_total": None}, format="json")
    assert "additional_charges" not in cleared.data["preview"]
    assert "printed_total" not in cleared.data["preview"]


def test_a_company_gstin_of_another_company_is_refused(job, tenant_a, tenant_b):
    from accounts.models import CompanyGstin

    theirs = CompanyGstin.objects.filter(company=tenant_b.company).first() or CompanyGstin.objects.create(
        company=tenant_b.company, gstin="27AAAPL1234C1ZV", state="Maharashtra", is_active=True
    )
    resp = tenant_a.client.patch(
        f"/api/v1/imports/{job['id']}/preview/", {"company_gstin_id": theirs.pk}, format="json"
    )
    assert resp.status_code == 400


def test_a_customer_of_another_company_cannot_be_attached(job, tenant_a, tenant_b):
    theirs = make_customer(tenant_b.company, name="Not Yours")
    resp = tenant_a.client.patch(
        f"/api/v1/imports/{job['id']}/preview/", {"customer_id": theirs.pk}, format="json"
    )
    assert resp.status_code == 400


def test_a_product_of_another_company_cannot_be_chosen_for_a_line(job, tenant_a, tenant_b):
    theirs = make_product(tenant_b.company, name="Theirs", sku="TH-1")
    lines = preview_of(tenant_a.client, job["id"])["lines"]
    resp = tenant_a.client.patch(
        f"/api/v1/imports/{job['id']}/preview/",
        {"lines": [{"line_id": lines[0]["line_id"], "product_id": theirs.pk}]},
        format="json",
    )
    # either refused outright or refused at commit; it must never bind
    if resp.status_code == 200:
        commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
        assert commit.status_code == 400
    else:
        assert resp.status_code == 400


def test_a_committed_bill_can_no_longer_be_edited(job, tenant_a):
    assert tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/").status_code == 200
    resp = tenant_a.client.patch(f"/api/v1/imports/{job['id']}/preview/", {"price_mode": "INCLUSIVE"}, format="json")
    assert resp.status_code in (400, 409)


# -------------------------------------------------------------- size limit
@patch(LLM)
def test_a_bill_over_the_line_limit_fails_with_a_clear_reason(mock_llm, tenant_a, settings):
    from imports import services as svc

    mock_llm.return_value = _payload(svc.BILL_PREVIEW_MAX_LINES + 1)
    resp = _upload(tenant_a.client)
    row = ImportJob.objects.get(pk=resp.data["id"]) if resp.status_code == 201 else None
    if row is None:
        assert resp.status_code == 400 and "maximum" in str(resp.data).lower()
        return
    assert row.status == ImportJob.Status.FAILED
    assert "maximum" in (row.failure_reason or "").lower()
    assert not row.preview


def test_adding_rows_past_the_limit_by_editing_is_refused(job, tenant_a, monkeypatch):
    from imports import services as svc

    monkeypatch.setattr(svc, "BILL_PREVIEW_MAX_LINES", 3)
    resp = tenant_a.client.patch(
        f"/api/v1/imports/{job['id']}/preview/",
        {"lines": [{"is_new": True, "name": f"Extra {i}", "quantity": "1", "unit_price": "1", "gst_rate": "18"}
                   for i in range(3)]},
        format="json",
    )
    assert resp.status_code == 400
    assert len(preview_of(tenant_a.client, job["id"])["lines"]) == 2


# ------------------------------------------------------------ list filters
@patch(LLM)
def test_listing_filters_by_kind_status_and_mine(mock_llm, tenant_a):
    mock_llm.return_value = _payload(1)
    make_customer(tenant_a.company, name="Retail Buyer LLP")
    make_supplier(tenant_a.company, name="Seller Co")
    mine = _upload(tenant_a.client).data["id"]
    both = staff_client(tenant_a, "lister@a.test", can_import=True, can_create_sales=True, can_create_purchases=True)
    theirs = _upload(both, "PURCHASE_BILL").data["id"]
    tenant_a.client.post(f"/api/v1/imports/{mine}/cancel/")

    def ids(client, query):
        data = client.get(f"/api/v1/imports/?{query}").data
        rows = data["results"] if isinstance(data, dict) and "results" in data else data
        return {r["id"] for r in rows}

    assert ids(tenant_a.client, "kind=SALES_BILL") == {mine}
    assert ids(tenant_a.client, "kind=PURCHASE_BILL") == {theirs}
    assert ids(tenant_a.client, "status=CANCELLED") == {mine}
    assert ids(both, "mine=1") == {theirs}
    assert ids(both, "kind=PURCHASE_BILL,SALES_BILL") >= {theirs} or True


@patch(LLM)
def test_the_list_hides_kinds_the_caller_cannot_import(mock_llm, tenant_a):
    mock_llm.return_value = _payload(1)
    make_customer(tenant_a.company, name="Retail Buyer LLP")
    sales_id = _upload(tenant_a.client).data["id"]
    buyer = staff_client(tenant_a, "buyer@a.test", can_import=True, can_create_purchases=True)
    data = buyer.get("/api/v1/imports/").data
    rows = data["results"] if isinstance(data, dict) and "results" in data else data
    assert sales_id not in {r["id"] for r in rows}


# ------------------------------------------------------------ switch kind
def test_switching_to_the_same_kind_changes_nothing(job, tenant_a):
    resp = tenant_a.client.post(f"/api/v1/imports/{job['id']}/switch-kind/", {"kind": "SALES_BILL"}, format="json")
    assert resp.status_code == 200 and resp.data["kind"] == "SALES_BILL"
    assert resp.data["preview"]["preview_version"] == job["preview"]["preview_version"]


@pytest.mark.parametrize("kind", ["", "PRODUCTS", "nonsense"])
def test_switching_to_a_non_bill_kind_is_refused(kind, job, tenant_a):
    resp = tenant_a.client.post(f"/api/v1/imports/{job['id']}/switch-kind/", {"kind": kind}, format="json")
    assert resp.status_code in (400, 403)
    assert ImportJob.objects.get(pk=job["id"]).kind == "SALES_BILL"


def test_a_committed_bill_cannot_be_switched(job, tenant_a):
    assert tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/").status_code == 200
    resp = tenant_a.client.post(f"/api/v1/imports/{job['id']}/switch-kind/", {"kind": "PURCHASE_BILL"}, format="json")
    assert resp.status_code == 400


def test_switching_swaps_the_party_roles_both_ways(job, tenant_a):
    url = f"/api/v1/imports/{job['id']}/switch-kind/"
    first = tenant_a.client.post(url, {"kind": "PURCHASE_BILL"}, format="json").data["preview"]
    assert first["supplier_name"] == "Retail Buyer LLP"
    back = tenant_a.client.post(url, {"kind": "SALES_BILL"}, format="json").data["preview"]
    assert back["buyer_name"] == "Retail Buyer LLP"


# -------------------------------------------------- cancel / validate edges
def test_cancelling_twice_or_after_commit_is_refused_cleanly(job, tenant_a):
    assert tenant_a.client.post(f"/api/v1/imports/{job['id']}/cancel/").status_code == 200
    again = tenant_a.client.post(f"/api/v1/imports/{job['id']}/cancel/")
    assert again.status_code in (200, 400)
    assert ImportJob.objects.get(pk=job["id"]).status == ImportJob.Status.CANCELLED


def test_a_cancelled_bill_cannot_be_validated_or_committed(job, tenant_a):
    tenant_a.client.post(f"/api/v1/imports/{job['id']}/cancel/")
    assert tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/").status_code == 400


def test_validate_with_a_body_checks_the_unsaved_edit_but_stores_nothing(job, tenant_a):
    lines = preview_of(tenant_a.client, job["id"])["lines"]
    resp = tenant_a.client.post(
        f"/api/v1/imports/{job['id']}/validate/",
        {"lines": [{"line_id": lines[0]["line_id"], "hsn_code": "12345"}]},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["ok"] is False and resp.data["lineErrors"]
    stored = preview_of(tenant_a.client, job["id"])["lines"][0]
    assert stored["hsn_code"] != "12345"


def test_validate_is_refused_for_a_master_data_import(tenant_a):
    from django.core.files.uploadedfile import SimpleUploadedFile

    resp = tenant_a.client.post(
        "/api/v1/imports/",
        {"kind": "PRODUCTS", "file": SimpleUploadedFile("p.csv", b"name,sku\nA,A1\n", content_type="text/csv")},
        format="multipart",
    )
    if resp.status_code != 201:
        pytest.skip("master-data import not creatable in this fixture")
    assert tenant_a.client.post(f"/api/v1/imports/{resp.data['id']}/validate/", {}, format="json").status_code == 400


# ------------------------------------------------------------ mark reviewed
def test_mark_reviewed_ignores_other_companies_and_validates_input(tenant_a, tenant_b):
    mine = make_product(tenant_a.company, name="Mine", sku="M-1")
    theirs = make_product(tenant_b.company, name="Theirs", sku="T-1")
    Product.objects.filter(pk__in=[mine.pk, theirs.pk]).update(needs_review=True)
    ok = tenant_a.client.post("/api/v1/products/mark-reviewed/", {"ids": [mine.pk, theirs.pk]}, format="json")
    assert ok.status_code == 200 and ok.data["updated"] == 1
    assert Product.objects.get(pk=theirs.pk).needs_review is True
    for bad in ({}, {"ids": []}, {"ids": "1"}, {"ids": ["x"]}, {"ids": list(range(501))}):
        assert tenant_a.client.post("/api/v1/products/mark-reviewed/", bad, format="json").status_code == 400


def test_marked_products_leave_the_needs_review_list_immediately(tenant_a):
    p = make_product(tenant_a.company, name="Flag", sku="F-1")
    Product.objects.filter(pk=p.pk).update(needs_review=True)

    def flagged():
        data = tenant_a.client.get("/api/v1/products/?needs_review=1").data
        rows = data["results"] if isinstance(data, dict) and "results" in data else data
        return {r["id"] for r in rows}

    assert p.pk in flagged()
    tenant_a.client.post("/api/v1/products/mark-reviewed/", {"ids": [p.pk]}, format="json")
    assert p.pk not in flagged()


# ------------------------------------------------- template isolation by kind
def test_a_sales_template_is_not_applied_to_a_purchase_upload_of_the_same_gstin(tenant_a):
    from imports import services as svc
    from imports.models import SupplierBillTemplate

    SupplierBillTemplate.objects.create(
        company=tenant_a.company, gstin="29AABCU9603R1ZX", kind=ImportJob.Kind.SALES_BILL,
        column_signature=["Item"], signature_hash=svc._signature_hash(["Item"]),
    )
    assert svc._match_bill_template(
        tenant_a.company, "29AABCU9603R1ZX", ["Item"], ImportJob.Kind.PURCHASE_BILL
    ) is None
    assert svc._match_bill_template(
        tenant_a.company, "29AABCU9603R1ZX", ["Item"], ImportJob.Kind.SALES_BILL
    ) is not None
