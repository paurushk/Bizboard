"""SET-09: units show how many items use them and are not deleted out from under those items."""

from masters.models import Unit
from tests.conftest import make_product

URL = "/api/v1/masters/units/"


def _unit(tenant, name="Dozen", short="doz", uqc="DOZ"):
    return Unit.objects.create(company=tenant.company, name=name, short_name=short, uqc_code=uqc)


def test_usage_counts_items_per_unit_and_is_not_cached(tenant_a):
    dozen, kilo = _unit(tenant_a), _unit(tenant_a, "Kilogram", "kg", "KGS")
    for i in range(3):
        make_product(tenant_a.company, sku=f"U-{i}", unit=dozen)
    tenant_a.client.get(URL)  # warms the cached list
    first = tenant_a.client.get(URL + "usage/").data
    assert first == {str(dozen.id): 3}
    make_product(tenant_a.company, sku="U-9", unit=kilo)
    second = tenant_a.client.get(URL + "usage/").data
    assert second == {str(dozen.id): 3, str(kilo.id): 1}


def test_usage_does_not_count_another_companys_items(tenant_a, tenant_b):
    theirs = _unit(tenant_b, "Dozen", "doz", "DOZ")
    make_product(tenant_b.company, sku="T-1", unit=theirs)
    assert tenant_a.client.get(URL + "usage/").data == {}


def test_a_unit_used_by_items_is_not_deleted(tenant_a):
    unit = _unit(tenant_a)
    product = make_product(tenant_a.company, sku="USED-1", unit=unit)
    r = tenant_a.client.delete(f"{URL}{unit.id}/")
    assert r.status_code == 400 and "1 item" in str(r.data)
    assert Unit.objects.filter(pk=unit.pk).exists()
    product.refresh_from_db()
    assert product.unit_id == unit.id


def test_an_unused_unit_can_be_deleted_and_the_list_updates(tenant_a):
    unit = _unit(tenant_a)
    tenant_a.client.get(URL)
    assert tenant_a.client.delete(f"{URL}{unit.id}/").status_code == 204
    listed = tenant_a.client.get(URL).data
    rows = listed["results"] if isinstance(listed, dict) else listed
    assert unit.id not in [r["id"] for r in rows]


def test_only_the_owner_can_delete_a_unit(tenant_a):
    unit = _unit(tenant_a)
    assert tenant_a.staff_client.delete(f"{URL}{unit.id}/").status_code == 403


def test_a_made_up_unit_code_is_refused_and_a_real_one_is_kept(tenant_a):
    bad = tenant_a.client.post(URL, {"name": "Bundle2", "short_name": "bn2", "uqc_code": "ZZZ"}, format="json")
    assert bad.status_code == 400 and "uqc_code" in str(bad.data)
    ok = tenant_a.client.post(URL, {"name": "Litre", "short_name": "l", "uqc_code": "LTR"}, format="json")
    assert ok.status_code == 201 and ok.data["uqc_code"] == "LTR"
    assert Unit.objects.filter(company=tenant_a.company).count() == 1


def test_a_blank_code_is_still_worked_out_from_the_name(tenant_a):
    r = tenant_a.client.post(URL, {"name": "Pieces", "short_name": "pcs"}, format="json")
    assert r.status_code == 201 and r.data["uqc_code"] == "PCS"


def test_editing_a_unit_cannot_set_a_bad_code(tenant_a):
    unit = _unit(tenant_a)
    r = tenant_a.client.patch(f"{URL}{unit.id}/", {"uqc_code": "NOPE"}, format="json")
    assert r.status_code == 400
    unit.refresh_from_db()
    assert unit.uqc_code == "DOZ"
