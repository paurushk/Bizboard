"""Item custom fields — definitions, capture, search, filter, import snapshot."""

from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from inventory.models import MovementType
from inventory.services import InventoryService
from masters.custom_fields import (
    coerce_values,
    normalize_header,
    resolve_import_columns,
    validate_definitions,
)
from masters.models import Product
from tests.conftest import make_product

pytestmark = pytest.mark.django_db


def _defs(*rows):
    return validate_definitions([], list(rows))


def _set_defs(company, rows):
    company.item_custom_field_defs = validate_definitions(company.item_custom_field_defs or [], rows)
    company.save(update_fields=["item_custom_field_defs"])


def test_normalize_header_collapses_separators():
    assert normalize_header("Brand Code") == "brand code"
    assert normalize_header("brand_code") == "brand code"
    assert normalize_header("brandCode") == "brandcode"


def test_validate_definitions_empty_ok():
    assert validate_definitions([], []) == []


def test_validate_definitions_rejects_non_dict():
    with pytest.raises(Exception):
        validate_definitions([], ["not-an-object"])


def test_active_labels_unique_after_separator_normalize():
    with pytest.raises(Exception):
        _defs(
            {"key": "brandForm", "label": "Brand form", "type": "text", "active": True},
            {"key": "brandForm2", "label": "Brand_form", "type": "text", "active": True},
        )


def test_validate_definitions_rejects_reuse_and_delete():
    existing = _defs({"key": "color", "label": "Color", "type": "text", "active": True})
    with pytest.raises(Exception):
        validate_definitions(existing, [])
    with pytest.raises(Exception):
        validate_definitions(existing, [{"key": "COLOR", "label": "Shade", "type": "text", "active": True}])
    deactivated = validate_definitions(existing, [
        {"key": "color", "label": "Color", "type": "text", "active": False},
    ])
    assert deactivated[0]["active"] is False
    with pytest.raises(Exception):
        validate_definitions(deactivated, deactivated + [
            {"key": "color", "label": "Customer Ref", "type": "text", "active": True},
        ])


def test_label_unique_among_active_only():
    existing = _defs(
        {"key": "a", "label": "Color", "type": "text", "active": False},
        {"key": "b", "label": "Color", "type": "text", "active": True},
    )
    assert existing[0]["key"] == "b"
    with pytest.raises(Exception):
        validate_definitions(existing, [
            {"key": "b", "label": "Color", "type": "text", "active": True},
            {"key": "a", "label": "Color", "type": "text", "active": True},
        ])


def test_list_options_required_when_active():
    with pytest.raises(Exception):
        _defs({"key": "form", "label": "Form", "type": "list", "active": True, "options": []})
    ok = _defs({"key": "form", "label": "Form", "type": "list", "active": True, "options": ["Strip", "Bottle"]})
    assert ok[0]["options"] == ["Strip", "Bottle"]


def test_company_empty_defs_are_empty(tenant_a):
    resp = tenant_a.client.get("/api/v1/company/")
    assert resp.status_code == 200
    assert resp.data.get("item_custom_field_defs") in ([], None) or resp.data["item_custom_field_defs"] == []


def test_company_patch_defs_and_product_roundtrip(tenant_a):
    defs = [
        {"key": "color", "label": "Color", "type": "text", "active": True},
        {"key": "form", "label": "Brand form", "type": "list", "active": True, "options": ["Strip", "Bottle"]},
    ]
    resp = tenant_a.client.patch("/api/v1/company/", {"item_custom_field_defs": defs}, format="json")
    assert resp.status_code == 200, resp.data
    saved = resp.data["item_custom_field_defs"]
    assert [row["key"] for row in saved if row["active"]] == ["color", "form"]

    create = tenant_a.client.post("/api/v1/products/", {
        "name": "Amox", "sku": "AMX-1", "gst_rate": "18",
        "custom_fields": {"color": "Red", "form": "strip"},
    }, format="json")
    assert create.status_code == 201, create.data
    assert create.data["custom_fields"]["form"] == "Strip"
    assert create.data["custom_fields"]["color"] == "Red"

    bad = tenant_a.client.post("/api/v1/products/", {
        "name": "Bad", "sku": "BAD-1", "gst_rate": "18", "custom_fields": {"form": "Jar"},
    }, format="json")
    assert bad.status_code == 400

    unknown = tenant_a.client.post("/api/v1/products/", {
        "name": "Unk", "sku": "UNK-1", "gst_rate": "18", "custom_fields": {"nope": "x"},
    }, format="json")
    assert unknown.status_code == 400


def test_inactive_value_survives_resave(tenant_a):
    _set_defs(tenant_a.company, [
        {"key": "color", "label": "Color", "type": "text", "active": True},
        {"key": "ref", "label": "Ref", "type": "text", "active": True},
    ])
    product = make_product(tenant_a.company, sku="KEEP-1", name="Keep")
    product.custom_fields = {"color": "Red", "ref": "R-9"}
    product.save(update_fields=["custom_fields"])
    _set_defs(tenant_a.company, [
        {"key": "color", "label": "Color", "type": "text", "active": True},
        {"key": "ref", "label": "Ref", "type": "text", "active": False},
    ])
    tenant_a.company.refresh_from_db()
    resp = tenant_a.client.patch(f"/api/v1/products/{product.id}/", {
        "custom_fields": {"color": "Blue"},
    }, format="json")
    assert resp.status_code == 200, resp.data
    product.refresh_from_db()
    assert product.custom_fields.get("color") == "Blue"
    assert product.custom_fields.get("ref") == "R-9"
    assert "ref" not in (resp.data.get("custom_fields") or {})
    listed = tenant_a.client.get(f"/api/v1/products/{product.id}/")
    assert listed.status_code == 200
    assert listed.data["custom_fields"].get("color") == "Blue"
    assert "ref" not in (listed.data.get("custom_fields") or {})


def test_product_search_and_cf_filter(tenant_a):
    _set_defs(tenant_a.company, [
        {"key": "color", "label": "Color", "type": "text", "active": True},
        {"key": "form", "label": "Form", "type": "list", "active": True, "options": ["Strip", "Bottle"]},
    ])
    p1 = make_product(tenant_a.company, sku="S1", name="Alpha")
    p1.custom_fields = {"color": "Crimson", "form": "Strip"}
    p1.save(update_fields=["custom_fields"])
    p2 = make_product(tenant_a.company, sku="S2", name="Beta")
    p2.custom_fields = {"color": "Blue", "form": "Bottle"}
    p2.save(update_fields=["custom_fields"])

    found = tenant_a.client.get("/api/v1/products/", {"q": "crim"})
    ids = {row["id"] for row in found.data["results"]}
    assert p1.id in ids
    assert p2.id not in ids

    by_label = tenant_a.client.get("/api/v1/products/", {"q": "Color"})
    label_ids = {row["id"] for row in by_label.data["results"]}
    assert p1.id not in label_ids
    assert p2.id not in label_ids

    filtered = tenant_a.client.get("/api/v1/products/", {"cf.form": "Strip"})
    fids = {row["id"] for row in filtered.data["results"]}
    assert fids == {p1.id}

    ignored_text = tenant_a.client.get("/api/v1/products/", {"cf.color": "Crimson"})
    # text keys ignored — both items still returned (or at least not exclusive-filtered)
    ignored_ids = {row["id"] for row in ignored_text.data["results"]}
    assert p1.id in ignored_ids and p2.id in ignored_ids


def test_custom_fields_brand_query_filter(tenant_a):
    _set_defs(tenant_a.company, [
        {"key": "brandCode", "label": "Brand code", "type": "text", "active": True},
        {"key": "rack", "label": "Rack", "type": "text", "active": True},
    ])
    p1 = make_product(tenant_a.company, sku="BR-1", name="Amul milk")
    p1.custom_fields = {"brandCode": "AMUL", "rack": "A1"}
    p1.save(update_fields=["custom_fields"])
    p2 = make_product(tenant_a.company, sku="BR-2", name="Other milk")
    p2.custom_fields = {"brandCode": "NESTLE", "rack": "B2"}
    p2.save(update_fields=["custom_fields"])

    by_alias = tenant_a.client.get("/api/v1/products/", {"custom_fields.brand": "AMUL"})
    assert {row["id"] for row in by_alias.data["results"]} == {p1.id}
    by_key = tenant_a.client.get("/api/v1/products/", {"custom_fields.brandCode": "AMUL"})
    assert {row["id"] for row in by_key.data["results"]} == {p1.id}
    by_rack = tenant_a.client.get("/api/v1/products/", {"custom_fields.rack": "B2"})
    assert {row["id"] for row in by_rack.data["results"]} == {p2.id}


def test_stock_search_and_custom_fields_payload(tenant_a):
    _set_defs(tenant_a.company, [
        {"key": "form", "label": "Form", "type": "list", "active": True, "options": ["Strip", "Bottle"]},
    ])
    product = make_product(tenant_a.company, sku="ST-1", name="Stocky")
    product.custom_fields = {"form": "Strip"}
    product.save(update_fields=["custom_fields"])
    InventoryService.post_movement(
        company=tenant_a.company, product=product,
        movement_type=MovementType.OPENING_STOCK, quantity=Decimal("4"),
        user=tenant_a.owner,
    )
    listed = tenant_a.client.get("/api/v1/inventory/balances/", {"q": "strip"})
    assert listed.status_code == 200
    rows = listed.data["results"] if isinstance(listed.data, dict) else listed.data
    assert any(row.get("custom_fields", {}).get("form") == "Strip" or row.get("customFields", {}).get("form") == "Strip" for row in rows)

    filtered = tenant_a.client.get("/api/v1/inventory/balances/", {"cf.form": "Strip"})
    frows = filtered.data["results"] if isinstance(filtered.data, dict) else filtered.data
    assert frows


def _upload_products(tenant, content):
    return tenant.client.post("/api/v1/imports/", {
        "kind": "PRODUCTS",
        "file": SimpleUploadedFile("items.csv", content, content_type="text/csv"),
    }, format="multipart")


def test_import_matches_key_and_label_and_snapshot(tenant_a):
    _set_defs(tenant_a.company, [
        {"key": "color", "label": "Color", "type": "text", "active": True},
        {"key": "form", "label": "Brand form", "type": "list", "active": True, "options": ["Strip", "Bottle"]},
    ])
    csv_content = (
        b"name,sku,Color,brand_form\n"
        b"Amox,AM-1,Red,Strip\n"
    )
    job = _upload_products(tenant_a, csv_content).data
    assert job["error_rows"] == 0, job
    commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert commit.status_code == 200, commit.data
    product = Product.objects.get(company=tenant_a.company, sku="AM-1")
    assert product.custom_fields.get("color") == "Red"
    assert product.custom_fields.get("form") == "Strip"


def test_import_duplicate_headers_fail(tenant_a):
    _set_defs(tenant_a.company, [
        {"key": "color", "label": "Color", "type": "text", "active": True},
    ])
    csv_content = b"name,sku,Color,color\nA,A1,Red,Blue\n"
    resp = _upload_products(tenant_a, csv_content)
    assert resp.status_code == 400


def test_import_list_option_row_error(tenant_a):
    _set_defs(tenant_a.company, [
        {"key": "form", "label": "Form", "type": "list", "active": True, "options": ["Strip"]},
    ])
    csv_content = b"name,sku,Form\nA,A1,Jar\n"
    job = _upload_products(tenant_a, csv_content).data
    assert job["error_rows"] == 1
    assert any("option" in err.lower() for err in job["errors"][0]["errors"])


def test_import_commit_uses_snapshot_after_def_change(tenant_a):
    _set_defs(tenant_a.company, [
        {"key": "color", "label": "Color", "type": "text", "active": True},
    ])
    csv_content = b"name,sku,Color\nSnap,SNAP-1,Green\n"
    job = _upload_products(tenant_a, csv_content).data
    assert job["valid_rows"] == 1
    _set_defs(tenant_a.company, [
        {"key": "color", "label": "Shade", "type": "text", "active": True},
    ])
    commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert commit.status_code == 200, commit.data
    product = Product.objects.get(sku="SNAP-1")
    assert product.custom_fields.get("color") == "Green"


def test_template_omits_hardcoded_brand_columns(tenant_a):
    csv_resp = tenant_a.client.get("/api/v1/imports/template/", {"kind": "PRODUCTS", "as": "csv"})
    header = csv_resp.content.decode().splitlines()[0]
    assert "brand_code" not in header.split(",")
    _set_defs(tenant_a.company, [
        {"key": "color", "label": "Color", "type": "text", "active": True},
    ])
    csv_resp = tenant_a.client.get("/api/v1/imports/template/", {"kind": "PRODUCTS", "as": "csv"})
    header = csv_resp.content.decode().splitlines()[0]
    assert "Color" in header.split(",")


def test_resolve_import_columns_duplicate_target():
    defs = _defs({"key": "color", "label": "Color", "type": "text", "active": True})
    _mapping, errors = resolve_import_columns(["Color", "color"], defs)
    assert errors


def test_migration_seeds_brand_only_when_present(tenant_a, tenant_b):
    import importlib

    from django.apps import apps

    migration = importlib.import_module("accounts.migrations.0033_custom_field_defs_shape")

    product = make_product(tenant_a.company, sku="BRAND-1", name="Branded")
    product.custom_fields = {"brandCode": "AMUL"}
    product.save(update_fields=["custom_fields"])
    tenant_a.company.item_custom_field_defs = [{"key": "rack", "label": "Rack"}]
    tenant_a.company.save(update_fields=["item_custom_field_defs"])
    tenant_b.company.item_custom_field_defs = []
    tenant_b.company.save(update_fields=["item_custom_field_defs"])

    migration.forwards(apps, None)
    tenant_a.company.refresh_from_db()
    tenant_b.company.refresh_from_db()
    keys = [row["key"] for row in tenant_a.company.item_custom_field_defs]
    assert "rack" in keys
    assert "brandCode" in keys
    assert "brandForm" in keys
    assert "subBrandForm" in keys
    assert all("type" in row and "active" in row for row in tenant_a.company.item_custom_field_defs)
    assert tenant_b.company.item_custom_field_defs == []


def test_reserved_key_rejected():
    with pytest.raises(Exception):
        _defs({"key": "sku", "label": "Our SKU", "type": "text", "active": True})
    with pytest.raises(Exception):
        _defs({"key": "color", "label": "Name", "type": "text", "active": True})
    with pytest.raises(Exception):
        _defs({"key": "contains", "label": "Contains", "type": "text", "active": True})
    with pytest.raises(Exception):
        _defs({"key": "isnull", "label": "Is null", "type": "text", "active": True})


def test_coerce_maps_underscoreized_camel_keys():
    defs = _defs(
        {"key": "brandCode", "label": "Brand code", "type": "text", "active": True},
        {"key": "brandForm", "label": "Brand form", "type": "list", "active": True, "options": ["Strip", "Bottle"]},
    )
    out = coerce_values({"brand_code": "AMUL", "brand_form": "strip"}, defs, None)
    assert out == {"brandCode": "AMUL", "brandForm": "Strip"}


def test_product_write_preserves_camelcase_custom_keys(tenant_a):
    """Frontend axios sends customFields: { brandCode } — parser must not snake inner keys."""
    _set_defs(tenant_a.company, [
        {"key": "brandCode", "label": "Brand code", "type": "text", "active": True},
        {"key": "brandForm", "label": "Brand form", "type": "list", "active": True, "options": ["Strip", "Bottle"]},
    ])
    create = tenant_a.client.post("/api/v1/products/", {
        "name": "Amul",
        "sku": "BRAND-CF",
        "gstRate": "18",
        "customFields": {"brandCode": "AMUL", "brandForm": "strip"},
    }, format="json")
    assert create.status_code == 201, create.data
    assert create.data["custom_fields"]["brandCode"] == "AMUL"
    assert create.data["custom_fields"]["brandForm"] == "Strip"
    stored = Product.objects.get(company=tenant_a.company, sku="BRAND-CF")
    assert stored.custom_fields["brandCode"] == "AMUL"
    assert stored.custom_fields["brandForm"] == "Strip"

    patch = tenant_a.client.patch(f"/api/v1/products/{stored.id}/", {
        "customFields": {"brandCode": "AMUL-X", "brandForm": "Bottle"},
    }, format="json")
    assert patch.status_code == 200, patch.data
    stored.refresh_from_db()
    assert stored.custom_fields["brandCode"] == "AMUL-X"
    assert stored.custom_fields["brandForm"] == "Bottle"


def test_import_update_merges_custom_fields_and_keeps_inactive(tenant_a):
    _set_defs(tenant_a.company, [
        {"key": "color", "label": "Color", "type": "text", "active": True},
        {"key": "form", "label": "Form", "type": "list", "active": True, "options": ["Strip", "Bottle"]},
        {"key": "oldCode", "label": "Old code", "type": "text", "active": False},
    ])
    product = make_product(tenant_a.company, sku="AM-1", name="Amox")
    product.custom_fields = {"color": "Red", "form": "Strip", "oldCode": "LEGACY"}
    product.barcode = "111"
    product.save(update_fields=["custom_fields", "barcode"])
    csv_content = b"name,sku,barcode,Color\nAmox Plus,AM-1,111,Blue\n"
    job = _upload_products(tenant_a, csv_content).data
    assert job["error_rows"] == 0, job
    commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert commit.status_code == 200, commit.data
    product.refresh_from_db()
    assert product.name == "Amox Plus"
    assert product.custom_fields.get("color") == "Blue"
    assert product.custom_fields.get("form") == "Strip"
    assert product.custom_fields.get("oldCode") == "LEGACY"
    assert product.barcode == "111"


def test_import_update_foreign_barcode_still_rejected(tenant_a):
    _set_defs(tenant_a.company, [
        {"key": "color", "label": "Color", "type": "text", "active": True},
    ])
    make_product(tenant_a.company, sku="AM-1", name="Amox", barcode="111")
    other = make_product(tenant_a.company, sku="OT-1", name="Other")
    other.barcode = "222"
    other.save(update_fields=["barcode"])
    csv_content = b"name,sku,barcode,Color\nAmox,AM-1,222,Blue\n"
    job = _upload_products(tenant_a, csv_content).data
    assert job["error_rows"] == 1
    assert any("barcode" in err.lower() for err in job["errors"][0]["errors"])


def test_custom_field_values_includes_stored_orphans(tenant_a):
    _set_defs(tenant_a.company, [
        {"key": "form", "label": "Form", "type": "list", "active": True, "options": ["Strip", "Bottle"]},
        {"key": "color", "label": "Color", "type": "text", "active": True},
    ])
    p1 = make_product(tenant_a.company, sku="V1", name="One")
    p1.custom_fields = {"form": "Strip", "color": "Red"}
    p1.save(update_fields=["custom_fields"])
    p2 = make_product(tenant_a.company, sku="V2", name="Two")
    p2.custom_fields = {"form": "Jar"}
    p2.save(update_fields=["custom_fields"])
    resp = tenant_a.client.get("/api/v1/products/custom-field-values/")
    assert resp.status_code == 200, resp.data
    assert set(resp.data.get("form") or []) == {"Strip", "Jar"}
    assert "color" not in resp.data


def test_import_reassign_released_barcode(tenant_a):
    _set_defs(tenant_a.company, [
        {"key": "color", "label": "Color", "type": "text", "active": True},
    ])
    make_product(tenant_a.company, sku="AM-1", name="Amox", barcode="111")
    csv_content = (
        b"name,sku,barcode,Color\n"
        b"Amox Plus,AM-1,222,Blue\n"
        b"New Item,NEW-1,111,Red\n"
    )
    job = _upload_products(tenant_a, csv_content).data
    assert job["error_rows"] == 0, job
    commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert commit.status_code == 200, commit.data
    assert Product.objects.get(company=tenant_a.company, sku="AM-1").barcode == "222"
    assert Product.objects.get(company=tenant_a.company, sku="NEW-1").barcode == "111"


def test_item_custom_fields_v2_flag_default_on(tenant_a):
    resp = tenant_a.client.get("/api/v1/feature-flags/")
    assert resp.status_code == 200
    assert resp.data["item_custom_fields_v2"] is True
    tenant_a.company.feature_flags = {"item_custom_fields_v2": False}
    tenant_a.company.save(update_fields=["feature_flags"])
    resp = tenant_a.client.get("/api/v1/feature-flags/")
    assert resp.data["item_custom_fields_v2"] is False


def test_active_key_and_label_tokens_must_not_collide():
    with pytest.raises(Exception):
        _defs(
            {"key": "color", "label": "Shade", "type": "text", "active": True},
            {"key": "tint", "label": "Color", "type": "text", "active": True},
        )


def test_reactivate_appends_to_end_of_actives():
    existing = _defs(
        {"key": "color", "label": "Color", "type": "text", "active": True},
        {"key": "form", "label": "Form", "type": "list", "active": False, "options": ["Strip"]},
        {"key": "size", "label": "Size", "type": "text", "active": True},
    )
    result = validate_definitions(existing, [
        {"key": "color", "label": "Color", "type": "text", "active": True},
        {"key": "form", "label": "Form", "type": "list", "active": True, "options": ["Strip"]},
        {"key": "size", "label": "Size", "type": "text", "active": True},
    ])
    assert [row["key"] for row in result if row["active"]] == ["color", "size", "form"]


def test_orphan_list_value_accepted_case_insensitive(tenant_a):
    _set_defs(tenant_a.company, [
        {"key": "form", "label": "Form", "type": "list", "active": True, "options": ["Strip"]},
    ])
    product = make_product(tenant_a.company, sku="ORPH-1", name="Orphan")
    product.custom_fields = {"form": "Jar"}
    product.save(update_fields=["custom_fields"])
    resp = tenant_a.client.patch(f"/api/v1/products/{product.id}/", {
        "custom_fields": {"form": "jar"},
    }, format="json")
    assert resp.status_code == 200, resp.data
    product.refresh_from_db()
    assert product.custom_fields.get("form") == "Jar"


def test_cf_filter_or_within_key_and_across_keys(tenant_a):
    _set_defs(tenant_a.company, [
        {"key": "form", "label": "Form", "type": "list", "active": True, "options": ["Strip", "Bottle"]},
        {"key": "pack", "label": "Pack", "type": "list", "active": True, "options": ["Box", "Pouch"]},
    ])
    p1 = make_product(tenant_a.company, sku="F1", name="One")
    p1.custom_fields = {"form": "Strip", "pack": "Box"}
    p1.save(update_fields=["custom_fields"])
    p2 = make_product(tenant_a.company, sku="F2", name="Two")
    p2.custom_fields = {"form": "Strip", "pack": "Pouch"}
    p2.save(update_fields=["custom_fields"])
    p3 = make_product(tenant_a.company, sku="F3", name="Three")
    p3.custom_fields = {"form": "Bottle", "pack": "Box"}
    p3.save(update_fields=["custom_fields"])

    either_form = tenant_a.client.get("/api/v1/products/?cf.form=Strip&cf.form=Bottle")
    assert {row["id"] for row in either_form.data["results"]} == {p1.id, p2.id, p3.id}

    and_filter = tenant_a.client.get("/api/v1/products/?cf.form=Strip&cf.pack=Box")
    assert {row["id"] for row in and_filter.data["results"]} == {p1.id}


def test_import_commit_fails_when_mapped_key_removed(tenant_a):
    _set_defs(tenant_a.company, [
        {"key": "color", "label": "Color", "type": "text", "active": True},
    ])
    csv_content = b"name,sku,Color\nGone,GONE-1,Red\n"
    job = _upload_products(tenant_a, csv_content).data
    assert job["error_rows"] == 0, job
    tenant_a.company.item_custom_field_defs = []
    tenant_a.company.save(update_fields=["item_custom_field_defs"])
    commit = tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/")
    assert commit.status_code == 400
