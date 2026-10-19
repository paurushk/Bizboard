"""SET-11b: the optimistic lock on the other settings endpoints (company, rules, gateway, units, price lists, users)."""

from datetime import timedelta

import pytest

from accounts.models import Company
from masters.models import PriceList, Unit

COMPANY = "/api/v1/company/"
RULES = "/api/v1/payments/money-in-rules/"
GATEWAY = "/api/v1/payments/gateway-settings/"


def _bump(company):
    Company.objects.filter(pk=company.pk).update(updated_at=company.updated_at + timedelta(seconds=5))
    company.refresh_from_db()


@pytest.mark.parametrize(
    "url,body",
    [(COMPANY, {"city": "Pune"}), (RULES, {"cash_269st_mode": "warn"}), (GATEWAY, {"test_mode": False})],
)
def test_company_level_settings_refuse_a_stale_write_and_accept_a_current_one(tenant_a, url, body):
    first = tenant_a.client.get(url).data["updated_at"]
    ok = tenant_a.client.patch(url, {**body, "expected_updated_at": first}, format="json")
    assert ok.status_code == 200, ok.data
    latest = tenant_a.client.get(url).data["updated_at"]
    _bump(tenant_a.company)
    stale = tenant_a.client.patch(url, {**body, "expected_updated_at": latest}, format="json")
    assert stale.status_code == 409, stale.data
    # No timestamp sent: last write wins, as before.
    assert tenant_a.client.patch(url, body, format="json").status_code == 200


def test_unit_and_price_list_edits_are_locked_and_creates_are_idempotent(tenant_a):
    unit = Unit.objects.create(company=tenant_a.company, name="Box", short_name="BOX", uqc_code="BOX")
    url = f"/api/v1/masters/units/{unit.id}/"
    stamp = tenant_a.client.get(url).data["updated_at"]
    Unit.objects.filter(pk=unit.pk).update(updated_at=unit.updated_at + timedelta(seconds=5))
    assert tenant_a.client.patch(url, {"name": "Boxes", "expected_updated_at": stamp}, format="json").status_code == 409

    pl = PriceList.objects.create(company=tenant_a.company, name="Retail")
    purl = f"/api/v1/masters/price-lists/{pl.id}/"
    pstamp = tenant_a.client.get(purl).data["updated_at"]
    PriceList.objects.filter(pk=pl.pk).update(updated_at=pl.updated_at + timedelta(seconds=5))
    assert tenant_a.client.patch(purl, {"name": "Retail 2", "expected_updated_at": pstamp}, format="json").status_code == 409

    key = {"HTTP_IDEMPOTENCY_KEY": "unit-create-1"}
    first = tenant_a.client.post("/api/v1/masters/units/", {"name": "Dozen", "short_name": "DOZ", "uqc_code": "DOZ"}, format="json", **key)
    second = tenant_a.client.post("/api/v1/masters/units/", {"name": "Dozen", "short_name": "DOZ", "uqc_code": "DOZ"}, format="json", **key)
    assert first.status_code == 201 and second.status_code == 201
    assert Unit.objects.filter(company=tenant_a.company, name="Dozen").count() == 1


def test_user_membership_edit_is_locked(tenant_a):
    r = tenant_a.client.get("/api/v1/company/users/")
    rows = r.data["results"] if isinstance(r.data, dict) and "results" in r.data else r.data
    other = next(u for u in rows if u["role"] != "OWNER")
    url = f"/api/v1/company/users/{other['id']}/"
    from accounts.models import CompanyUser

    row = CompanyUser.objects.get(pk=other["id"])
    CompanyUser.objects.filter(pk=row.pk).update(updated_at=row.updated_at + timedelta(seconds=5))
    resp = tenant_a.client.patch(url, {"can_export": True, "expected_updated_at": other["updated_at"]}, format="json")
    assert resp.status_code == 409, resp.data
