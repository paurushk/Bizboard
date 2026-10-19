"""SET-09: past imports say who ran them and whether they can be undone; Tally runs can be listed."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from imports.models import ImportJob
from integrations.models import IntegrationSyncRun

pytestmark = pytest.mark.django_db

CUSTOMERS_CSV = b"name,phone,gstin,state\nRavi Stores,9800000001,,Karnataka\n,9800000003,,Karnataka\n"
PRODUCTS_CSV = b"name,sku,hsn_code,gst_rate,selling_price\nWidget,W-1,1001,18,100\n"
RUNS = "/api/v1/integrations/tally/runs/"


def _upload(tenant, kind, content):
    r = tenant.client.post(
        "/api/v1/imports/",
        {"kind": kind, "file": SimpleUploadedFile("data.csv", content, content_type="text/csv")},
        format="multipart",
    )
    assert r.status_code == 201, r.data
    return r.data


def _rows(resp):
    return resp.data["results"] if isinstance(resp.data, dict) else resp.data


def _by_id(tenant):
    return {row["id"]: row for row in _rows(tenant.client.get("/api/v1/imports/"))}


def test_a_job_names_who_uploaded_it_and_the_file(tenant_a):
    job = _upload(tenant_a, "customers", CUSTOMERS_CSV)
    row = _by_id(tenant_a)[job["id"]]
    assert row["created_by_name"] and row["file_name"] == "data.csv"
    assert row["total_rows"] == 2 and row["error_rows"] == 1


def test_only_committed_product_and_stock_imports_can_be_undone(tenant_a):
    customers = _upload(tenant_a, "customers", CUSTOMERS_CSV)
    products = _upload(tenant_a, "products", PRODUCTS_CSV)
    assert not _by_id(tenant_a)[products["id"]]["can_undo"]  # not committed yet
    for job in (customers, products):
        assert tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/").status_code == 200
    rows = _by_id(tenant_a)
    assert rows[products["id"]]["can_undo"] is True
    assert rows[customers["id"]]["can_undo"] is False  # customers cannot be undone
    ImportJob.objects.filter(pk=products["id"]).update(status=ImportJob.Status.VOIDED)
    assert _by_id(tenant_a)[products["id"]]["can_undo"] is False


def test_history_stays_inside_the_company(tenant_a, tenant_b):
    job = _upload(tenant_b, "customers", CUSTOMERS_CSV)
    assert job["id"] not in _by_id(tenant_a)


def test_listing_does_not_query_per_job(tenant_a, django_assert_max_num_queries):
    for _ in range(6):
        _upload(tenant_a, "customers", CUSTOMERS_CSV)
    with django_assert_max_num_queries(14):
        assert len(_rows(tenant_a.client.get("/api/v1/imports/"))) == 6


# ---- Tally runs ---------------------------------------------------------------------------------


def _run(tenant, status="PREVIEWED", customers=0, errors=0):
    return IntegrationSyncRun.objects.create(
        company=tenant.company, kind=IntegrationSyncRun.Kind.TALLY_IMPORT, status=status,
        preview={"customers": [{}] * customers, "suppliers": [], "products": []}, errors=[{"row": 1, "error": "x"}] * errors,
        created_by=tenant.owner,
    )


@override_settings(ENABLE_TALLY=True)
def test_tally_runs_are_listed_newest_first_with_counts_and_who(tenant_a):
    first = _run(tenant_a, "COMMITTED", customers=3)
    second = _run(tenant_a, "PREVIEWED", customers=1, errors=2)
    rows = tenant_a.client.get(RUNS).data
    assert [r["id"] for r in rows] == [second.id, first.id]
    assert rows[0]["customers"] == 1 and rows[0]["error_count"] == 2 and rows[0]["by"]
    assert rows[1]["status"] == "COMMITTED"


@override_settings(ENABLE_TALLY=True)
def test_tally_runs_show_only_imports_of_this_company_and_at_most_twenty(tenant_a, tenant_b):
    for _ in range(22):
        _run(tenant_a)
    _run(tenant_b)
    IntegrationSyncRun.objects.create(company=tenant_a.company, kind=IntegrationSyncRun.Kind.TALLY_EXPORT)
    assert len(tenant_a.client.get(RUNS).data) == 20


@override_settings(ENABLE_TALLY=True)
def test_tally_runs_need_the_import_permission(tenant_a):
    assert tenant_a.staff_client.get(RUNS).status_code == 403


@override_settings(ENABLE_TALLY=False)
def test_tally_runs_are_not_found_when_tally_is_not_switched_on(tenant_a):
    assert tenant_a.client.get(RUNS).status_code == 404


def test_history_can_be_filtered_by_type_and_paged(tenant_a):
    _upload(tenant_a, "customers", CUSTOMERS_CSV)
    _upload(tenant_a, "customers", CUSTOMERS_CSV)
    _upload(tenant_a, "products", PRODUCTS_CSV)
    only_products = tenant_a.client.get("/api/v1/imports/", {"kind": "PRODUCTS"})
    assert [r["kind"] for r in _rows(only_products)] == ["PRODUCTS"]
    first = tenant_a.client.get("/api/v1/imports/", {"page": 1, "page_size": 2})
    assert first.data["count"] == 3 and len(first.data["results"]) == 2 and first.data["next"]
    second = tenant_a.client.get("/api/v1/imports/", {"page": 2, "page_size": 2})
    assert len(second.data["results"]) == 1 and second.data["previous"]
    mine = tenant_a.client.get("/api/v1/imports/", {"mine": "1"})
    assert mine.data["count"] == 3


def test_another_company_imports_never_appear(tenant_a, tenant_b):
    _upload(tenant_b, "customers", CUSTOMERS_CSV)
    assert tenant_a.client.get("/api/v1/imports/").data["count"] == 0
