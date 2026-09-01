"""Sprint 1 dogfood baseline: invite, money-doc immutability, AA dark, OTP, flags."""

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from tests.conftest import make_customer

pytestmark = pytest.mark.django_db


def test_bb_000676_invite_returns_token_without_password(tenant_a):
    resp = tenant_a.client.post(
        "/api/v1/company/users/",
        {"email": "newstaff@alpha.test", "role": "SALES_STAFF", "full_name": "New Staff"},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    body = resp.data.get("data", resp.data)
    assert body.get("invite_token")


def test_bb_000675_invite_owner_rejected(tenant_a):
    resp = tenant_a.client.post(
        "/api/v1/company/users/",
        {"email": "coowner@alpha.test", "role": "OWNER"},
        format="json",
    )
    assert resp.status_code == 400


def test_bb_000650_receipt_hard_delete_forbidden(tenant_a):
    customer = make_customer(tenant_a.company)
    created = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {"customer": customer.id, "amount": "10.00", "mode": "CASH"},
        format="json",
    )
    assert created.status_code == 201, created.data
    rid = (created.data.get("data") or created.data)["id"]
    deleted = tenant_a.client.delete(f"/api/v1/payments/receipts/{rid}/")
    assert deleted.status_code in (404, 405)


@override_settings(ENABLE_ACCOUNT_AGGREGATOR=False)
def test_bb_000680_aa_404_when_flag_off(tenant_a):
    resp = tenant_a.client.get("/api/v1/banking/aa/")
    assert resp.status_code == 404


def test_bb_000633_otp_rejects_non_e164():
    client = APIClient()
    resp = client.post("/api/v1/auth/otp/request/", {"phone": "not-a-phone"}, format="json")
    assert resp.status_code == 400


def test_bb_000607_company_is_gst_registered(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.registration_type = tenant_a.company.RegistrationType.REGULAR
    tenant_a.company.save()
    assert tenant_a.company.is_gst_registered is True
