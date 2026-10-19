"""SET-08: the backup screen reports what really happened; restoring over live data is not self-service."""

import base64
import csv
import io

import pytest
from django.core.cache import cache
from django.test import override_settings

from accounts.models import Company, CompanyUser
from core.models import AuditEvent
from masters.models import PriceList, PriceListItem
from tests.conftest import make_customer, make_product, make_supplier

EXPORT = "/api/v1/company/export/"
LAST = "/api/v1/company/export/last/"
RESTORE = "/api/v1/company/restore/"


@pytest.fixture(autouse=True)
def _fresh_cache():
    cache.clear()
    yield
    cache.clear()


def _backup(tenant):
    r = tenant.client.post(EXPORT, {}, format="json")
    assert r.status_code == 200, getattr(r, "data", r.content[:200])
    cache.clear()  # the 10-minute lock is not what these tests are about
    return r.content


# ---- last backup ------------------------------------------------------------------------------


def test_no_backup_yet_is_reported_as_none(tenant_a):
    r = tenant_a.client.get(LAST)
    assert r.status_code == 200 and r.data["last_export"] is None


def test_the_last_backup_is_read_from_what_really_happened(tenant_a):
    make_customer(tenant_a.company)
    make_supplier(tenant_a.company)
    make_product(tenant_a.company, sku="BK-1")
    blob = _backup(tenant_a)
    last = tenant_a.client.get(LAST).data["last_export"]
    assert last["bytes"] == len(blob)
    assert last["exported_at"] is not None and last["version"]
    assert last["by"]
    summary = last["summary"]
    assert summary["customers"] >= 1 and summary["suppliers"] == 1 and summary["products"] == 1
    assert summary["records"] >= 3 and summary["sections"] >= 3
    for key in ("files_with_bytes", "files_listed_only", "file_warnings"):
        assert key in summary


def test_the_latest_of_several_backups_is_shown(tenant_a):
    _backup(tenant_a)
    make_customer(tenant_a.company, name="Added later")
    second = _backup(tenant_a)
    last = tenant_a.client.get(LAST).data["last_export"]
    assert last["bytes"] == len(second)
    assert last["summary"]["customers"] == 1


def test_one_company_never_sees_anothers_backup(tenant_a, tenant_b):
    _backup(tenant_b)
    assert tenant_a.client.get(LAST).data["last_export"] is None


def test_last_backup_is_owner_only(tenant_a):
    assert tenant_a.staff_client.get(LAST).status_code == 403


def test_the_page_states_whether_restoring_over_live_data_is_possible(tenant_a):
    with override_settings(TENANT_RESTORE_DESTROY_ENABLED=False):
        data = tenant_a.client.get(LAST).data
    assert data["restore_into_live_enabled"] is False and data["max_sandboxes"] >= 1
    with override_settings(TENANT_RESTORE_DESTROY_ENABLED=True):
        assert tenant_a.client.get(LAST).data["restore_into_live_enabled"] is True


# ---- restore ----------------------------------------------------------------------------------


def _restore(tenant, blob, **extra):
    return tenant.client.post(
        RESTORE, {"payload": base64.b64encode(blob).decode(), **extra}, format="json"
    )


@override_settings(TENANT_RESTORE_DESTROY_ENABLED=False)
def test_restoring_over_live_data_is_refused_by_default_and_nothing_changes(tenant_a):
    make_customer(tenant_a.company, name="Keep me")
    blob = _backup(tenant_a)
    make_customer(tenant_a.company, name="Added after")
    r = _restore(tenant_a, blob, confirm_destroy=True, typed_name=tenant_a.company.name)
    assert r.status_code == 400, r.data
    assert "support" in str(r.data).lower()
    from masters.models import Customer

    assert Customer.objects.filter(company=tenant_a.company).count() == 2
    assert not AuditEvent.objects.filter(company=tenant_a.company, action="tenant.restore_destroy").exists()


@override_settings(TENANT_RESTORE_DESTROY_ENABLED=False)
def test_a_sandbox_restore_still_works_when_live_restore_is_off(tenant_a):
    make_customer(tenant_a.company)
    blob = _backup(tenant_a)
    r = _restore(tenant_a, blob, restore="sandbox")
    assert r.status_code == 201, r.data
    assert r.data["mode"] == "sandbox" and r.data["sandbox_expires_at"]
    sandbox = Company.objects.get(pk=r.data["company_id"])
    assert sandbox.is_sandbox
    assert CompanyUser.objects.filter(company=sandbox, user=tenant_a.owner, role="OWNER").exists()


@override_settings(TENANT_RESTORE_DESTROY_ENABLED=True)
def test_when_support_enables_it_the_start_is_audited_before_the_restore(tenant_a):
    make_customer(tenant_a.company, name="Original")
    blob = _backup(tenant_a)
    r = _restore(
        tenant_a, blob, confirm_destroy=True, typed_name=tenant_a.company.name, confirm_destroy_unbacked=True
    )
    assert r.status_code == 200, r.data
    started = AuditEvent.objects.get(company=tenant_a.company, action="tenant.restore_destroy_started")
    done = AuditEvent.objects.get(company=tenant_a.company, action="tenant.restore_destroy")
    assert started.id < done.id


@override_settings(TENANT_RESTORE_DESTROY_ENABLED=True)
def test_the_typed_company_name_is_still_required_when_enabled(tenant_a):
    blob = _backup(tenant_a)
    r = _restore(tenant_a, blob, confirm_destroy=True, typed_name="wrong")
    assert r.status_code == 400 and "typed_name" in str(r.data)


# ---- more exports -----------------------------------------------------------------------------


def _csv(client, report, **params):
    r = client.get(f"/api/v1/exports/{report}/", params)
    assert r.status_code == 200, getattr(r, "data", r.content[:200])
    body = b"".join(r.streaming_content) if getattr(r, "streaming", False) else r.content
    return list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"))))


def test_the_item_master_export_lists_items_with_prices(tenant_a):
    p = make_product(tenant_a.company, name="Rice 5kg", sku="RICE-5", purchase_price="400", selling_price="450")
    rows = _csv(tenant_a.client, "products")
    row = next(r for r in rows if r["sku"] == "RICE-5")
    assert row["name"] == "Rice 5kg" and row["id"] == str(p.id)
    assert row["selling_price"] == "450.00" and row["purchase_price"] == "400.00"
    assert [r["sku"] for r in _csv(tenant_a.client, "items")] == [r["sku"] for r in rows]


def test_purchase_price_is_left_out_for_someone_without_margin_access(tenant_a):
    make_product(tenant_a.company, sku="COST-1", purchase_price="400", selling_price="450")
    CompanyUser.objects.filter(user=tenant_a.staff).update(can_export=True)
    r = tenant_a.staff_client.get("/api/v1/exports/products/")
    assert r.status_code == 200
    body = b"".join(r.streaming_content).decode("utf-8-sig")
    assert "selling_price" in body.splitlines()[0]
    assert "purchase_price" not in body and "400.00" not in body


def test_item_export_does_not_include_other_companies_or_deleted_items(tenant_a, tenant_b):
    make_product(tenant_b.company, sku="THEIRS-1")
    gone = make_product(tenant_a.company, sku="GONE-1")
    gone.is_deleted = True
    gone.save()
    make_product(tenant_a.company, sku="MINE-1")
    assert [r["sku"] for r in _csv(tenant_a.client, "products")] == ["MINE-1"]


def test_price_list_export_has_one_row_per_slab(tenant_a):
    product = make_product(tenant_a.company, sku="PL-1")
    plist = PriceList.objects.create(company=tenant_a.company, name="Wholesale")
    PriceListItem.objects.create(company=tenant_a.company, price_list=plist, product=product, unit_price="90", min_qty="1", max_qty="10")
    PriceListItem.objects.create(company=tenant_a.company, price_list=plist, product=product, unit_price="80", min_qty="11")
    rows = _csv(tenant_a.client, "price-lists")
    assert [(r["price_list"], r["sku"], r["min_qty"], r["max_qty"], r["unit_price"]) for r in rows] == [
        ("Wholesale", "PL-1", "1.000", "10.000", "90.00"),
        ("Wholesale", "PL-1", "11.000", "", "80.00"),
    ]


def test_an_empty_price_list_export_still_has_its_header_row(tenant_a):
    r = tenant_a.client.get("/api/v1/exports/price-lists/")
    header = b"".join(r.streaming_content).decode("utf-8-sig").splitlines()[0]
    assert header.startswith("price_list,")


def test_suppliers_can_be_exported(tenant_a):
    make_supplier(tenant_a.company, name="Mega Co")
    assert [r["name"] for r in _csv(tenant_a.client, "suppliers")] == ["Mega Co"]


def test_exports_still_need_the_export_permission(tenant_a):
    for report in ("products", "price-lists", "suppliers"):
        assert tenant_a.staff_client.get(f"/api/v1/exports/{report}/").status_code == 403
