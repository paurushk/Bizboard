"""SET-09: price lists show their size and users, and a list that is off really stops pricing."""

from decimal import Decimal

from masters.models import Customer, PriceList, PriceListItem
from masters.pricing import resolve_party_price
from tests.conftest import make_customer, make_product

URL = "/api/v1/masters/price-lists/"


def _list(tenant, name="Wholesale", slabs=1):
    plist = PriceList.objects.create(company=tenant.company, name=name)
    product = make_product(tenant.company, sku=f"PL-{name}", name=f"Item {name}")
    for i in range(slabs):
        PriceListItem.objects.create(
            company=tenant.company, price_list=plist, product=product, unit_price=Decimal("90") - i,
            min_qty=Decimal(1 + i * 10), max_qty=Decimal(10 + i * 10) if i < slabs - 1 else None,
        )
    return plist, product


def _rows(resp):
    return resp.data["results"] if isinstance(resp.data, dict) else resp.data


def test_each_list_reports_its_slab_count_and_customers(tenant_a):
    plist, _ = _list(tenant_a, slabs=3)
    make_customer(tenant_a.company, name="A", price_list=plist)
    gone = make_customer(tenant_a.company, name="B", price_list=plist)
    gone.is_deleted = True
    gone.save()
    row = next(r for r in _rows(tenant_a.client.get(URL)) if r["id"] == plist.id)
    assert row["item_count"] == 3 and row["customer_count"] == 1


def test_assigned_customers_are_named_and_stay_in_their_company(tenant_a, tenant_b):
    plist, _ = _list(tenant_a)
    make_customer(tenant_a.company, name="Zed", price_list=plist)
    make_customer(tenant_a.company, name="Amit", price_list=plist)
    assert [r["name"] for r in tenant_a.client.get(f"{URL}{plist.id}/customers/").data] == ["Amit", "Zed"]
    assert tenant_b.client.get(f"{URL}{plist.id}/customers/").status_code == 404


def test_a_list_nobody_uses_switches_off_freely(tenant_a):
    plist, _ = _list(tenant_a)
    r = tenant_a.client.patch(f"{URL}{plist.id}/", {"is_active": False}, format="json")
    assert r.status_code == 200 and r.data["is_active"] is False


def test_switching_off_a_list_customers_use_needs_confirmation(tenant_a):
    plist, _ = _list(tenant_a)
    make_customer(tenant_a.company, name="A", price_list=plist)
    refused = tenant_a.client.patch(f"{URL}{plist.id}/", {"is_active": False}, format="json")
    assert refused.status_code == 400 and "1 customer" in str(refused.data)
    plist.refresh_from_db()
    assert plist.is_active is True
    ok = tenant_a.client.patch(f"{URL}{plist.id}/", {"is_active": False, "confirm_customers": True}, format="json")
    assert ok.status_code == 200 and ok.data["is_active"] is False


def test_other_edits_to_a_list_in_use_need_no_confirmation(tenant_a):
    plist, _ = _list(tenant_a)
    make_customer(tenant_a.company, name="A", price_list=plist)
    assert tenant_a.client.patch(f"{URL}{plist.id}/", {"name": "Renamed"}, format="json").status_code == 200


def test_deleting_a_list_customers_use_needs_confirmation(tenant_a):
    plist, _ = _list(tenant_a)
    make_customer(tenant_a.company, name="A", price_list=plist)
    assert tenant_a.client.delete(f"{URL}{plist.id}/").status_code == 400
    assert PriceList.objects.filter(pk=plist.pk, is_deleted=False).exists()
    assert tenant_a.client.delete(f"{URL}{plist.id}/?confirm_customers=true").status_code == 204
    assert PriceList.all_objects.get(pk=plist.pk).is_deleted is True


def test_a_switched_off_list_no_longer_prices_its_customers(tenant_a):
    plist, product = _list(tenant_a)
    customer = make_customer(tenant_a.company, name="A", price_list=plist)
    price, name = resolve_party_price(customer=customer, product=product, quantity=Decimal("1"))
    assert price == Decimal("90") and name == "Wholesale"
    PriceList.objects.filter(pk=plist.pk).update(is_active=False)
    assert resolve_party_price(customer=Customer.objects.get(pk=customer.pk), product=product, quantity=Decimal("1")) == (None, "")


def test_a_deleted_list_no_longer_prices_its_customers(tenant_a):
    plist, product = _list(tenant_a)
    customer = make_customer(tenant_a.company, name="A", price_list=plist)
    PriceList.objects.filter(pk=plist.pk).update(is_deleted=True)
    assert resolve_party_price(customer=Customer.objects.get(pk=customer.pk), product=product, quantity=Decimal("1")) == (None, "")


def test_only_the_owner_can_change_a_price_list(tenant_a):
    plist, _ = _list(tenant_a)
    assert tenant_a.staff_client.patch(f"{URL}{plist.id}/", {"is_active": False}, format="json").status_code == 403
