"""Indian PIN codes are validated when the client changes them."""

import pytest

from masters.models import Customer

pytestmark = pytest.mark.django_db


def test_customer_create_rejects_invalid_pincode_and_stores_trimmed(tenant_a):
    rejected = tenant_a.client.post(
        "/api/v1/customers/",
        {"name": "Pin Reject", "pincode": "-1"},
        format="json",
    )
    assert rejected.status_code == 400
    assert "pincode" in rejected.data["error"]["details"]
    assert not Customer.objects.filter(company=tenant_a.company, name="Pin Reject").exists()

    for bad in ("abc", "5600", "000000", "1234567"):
        resp = tenant_a.client.post(
            "/api/v1/customers/",
            {"name": f"Pin {bad}", "pincode": bad},
            format="json",
        )
        assert resp.status_code == 400, bad

    created = tenant_a.client.post(
        "/api/v1/customers/",
        {"name": "Pin Ok", "pincode": " 560001 "},
        format="json",
    )
    assert created.status_code == 201, created.data
    body = created.data.get("data") or created.data
    assert body["pincode"] == "560001"

    blank = tenant_a.client.post(
        "/api/v1/customers/",
        {"name": "Pin Blank", "pincode": "   "},
        format="json",
    )
    assert blank.status_code == 201, blank.data
    blank_body = blank.data.get("data") or blank.data
    assert blank_body["pincode"] == ""

    edge = tenant_a.client.post(
        "/api/v1/customers/",
        {"name": "Pin Edge", "pincode": "100000"},
        format="json",
    )
    assert edge.status_code == 201, edge.data


def test_unchanged_legacy_pincode_can_be_resent(tenant_a):
    customer = Customer.objects.create(
        company=tenant_a.company, name="Legacy Pin", pincode="-1",
    )
    phone_only = tenant_a.client.patch(
        f"/api/v1/customers/{customer.id}/",
        {"phone": "9876543210"},
        format="json",
    )
    assert phone_only.status_code == 200, phone_only.data
    customer.refresh_from_db()
    assert customer.pincode == "-1"

    same = tenant_a.client.patch(
        f"/api/v1/customers/{customer.id}/",
        {"pincode": "-1"},
        format="json",
    )
    assert same.status_code == 200, same.data
    customer.refresh_from_db()
    assert customer.pincode == "-1"

    fixed = tenant_a.client.patch(
        f"/api/v1/customers/{customer.id}/",
        {"pincode": "560001"},
        format="json",
    )
    assert fixed.status_code == 200, fixed.data
    customer.refresh_from_db()
    assert customer.pincode == "560001"


def test_company_and_gstin_reject_a_new_invalid_pincode(tenant_a):
    company = tenant_a.client.patch(
        "/api/v1/company/",
        {"pincode": "-1"},
        format="json",
    )
    assert company.status_code == 400
    assert "pincode" in company.data["error"]["details"]

    stamp = tenant_a.client.post(
        "/api/v1/company/gstins/",
        {
            "gstin": "29ABCDE1234F1ZW",
            "legal_name": "HO",
            "state": "Karnataka",
            "pincode": "-1",
            "is_primary": False,
        },
        format="json",
    )
    assert stamp.status_code == 400
    assert "pincode" in stamp.data["error"]["details"]


def test_legacy_party_name_can_be_resaved_unchanged_but_not_changed_to_bad(tenant_a):
    customer = Customer.objects.create(company=tenant_a.company, name="<<>>")
    same = tenant_a.client.patch(
        f"/api/v1/customers/{customer.id}/", {"name": "<<>>", "phone": "9876543210"}, format="json",
    )
    assert same.status_code == 200, same.data
    bad = tenant_a.client.patch(
        f"/api/v1/customers/{customer.id}/", {"name": "<<!>>"}, format="json",
    )
    assert bad.status_code == 400
