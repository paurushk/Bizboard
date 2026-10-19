"""SET-09: custom fields say how many items hold a value before the field is removed."""

from tests.conftest import make_product

URL = "/api/v1/products/custom-field-usage/"


def _define(tenant, *keys, active=True):
    tenant.company.item_custom_field_defs = [
        {"key": k, "label": k.title(), "type": "text", "active": active, "options": []} for k in keys
    ]
    tenant.company.save(update_fields=["item_custom_field_defs"])


def _item(tenant, sku, fields):
    return make_product(tenant.company, sku=sku, custom_fields=fields)


def test_counts_items_with_a_value_per_field(tenant_a):
    _define(tenant_a, "colour", "size")
    _item(tenant_a, "CF-1", {"colour": "Red", "size": "M"})
    _item(tenant_a, "CF-2", {"colour": "Blue"})
    _item(tenant_a, "CF-3", {"colour": "", "size": "  "})
    _item(tenant_a, "CF-4", {})
    assert tenant_a.client.get(URL).data == {"colour": 2, "size": 1}


def test_counts_include_values_of_removed_fields_because_they_are_kept(tenant_a):
    _define(tenant_a, "legacy", active=False)
    _item(tenant_a, "CF-1", {"legacy": "x"})
    assert tenant_a.client.get(URL).data == {"legacy": 1}


def test_counts_stay_inside_the_company(tenant_a, tenant_b):
    _define(tenant_a, "colour")
    _item(tenant_b, "THEIRS", {"colour": "Red"})
    assert tenant_a.client.get(URL).data == {}


def test_staff_can_read_the_counts_and_they_carry_no_values(tenant_a):
    _item(tenant_a, "CF-1", {"colour": "Secret-Red"})
    r = tenant_a.staff_client.get(URL)
    assert r.status_code == 200
    assert "Secret-Red" not in str(r.data)
