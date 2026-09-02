from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import Company, CompanyUser
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product


pytestmark = pytest.mark.django_db


def test_invoice_audit_endpoint_returns_amend_diff(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(tenant_a, customer, [{"product": product.id, "quantity": "2", "unit_price": "100"}])
    completed = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert completed.status_code == 200, completed.data
    patched = tenant_a.client.patch(
        f"/api/v1/sales/invoices/{inv['id']}/",
        {
            "confirm_amend": True,
            "notes": "audited amend",
            "items": [{"product": product.id, "quantity": "2", "unit_price": "90"}],
        },
        format="json",
    )
    assert patched.status_code == 200, patched.data
    audit = tenant_a.client.get(f"/api/v1/sales/invoices/{inv['id']}/audit/")
    assert audit.status_code == 200, audit.data
    rows = audit.data if isinstance(audit.data, list) else audit.data.get("data") or audit.data.get("results")
    assert rows
    money = [r for r in rows if (r.get("metadata") or {}).get("before")]
    assert money
    before = Decimal(str(money[0]["metadata"]["before"]["grand_total"]))
    after = Decimal(str(money[0]["metadata"]["after"]["grand_total"]))
    assert before != after


def test_invoice_audit_hidden_from_sales_staff(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(tenant_a, customer, [{"product": product.id, "quantity": "1"}])
    tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    denied = tenant_a.staff_client.get(f"/api/v1/sales/invoices/{inv['id']}/audit/")
    assert denied.status_code in (403, 404)


def test_multi_membership_without_active_company_returns_409(tenant_a):
    other = Company.objects.create(name="Second Books", state="Delhi")
    CompanyUser.objects.create(
        company=other, user=tenant_a.owner, role=CompanyUser.Role.ACCOUNTANT,
        can_view_financial_reports=True, is_active=True,
    )
    tenant_a.owner.active_company = None
    tenant_a.owner.save(update_fields=["active_company"])
    client = APIClient()
    client.force_authenticate(user=tenant_a.owner)
    resp = client.get("/api/v1/company/")
    assert resp.status_code == 409, resp.data
    err = resp.data.get("error") or resp.data
    assert err.get("code") == "COMPANY_REQUIRED"
    details = err.get("details") or {}
    memberships = details.get("memberships") or []
    assert len(memberships) >= 2


def test_single_membership_without_active_company_does_not_409(tenant_a):
    tenant_a.owner.active_company = None
    tenant_a.owner.save(update_fields=["active_company"])
    resp = tenant_a.client.get("/api/v1/company/")
    assert resp.status_code == 200, resp.data


def test_feature_flags_company_required_returns_public_subset(tenant_a):
    other = Company.objects.create(name="Second Books", state="Delhi")
    CompanyUser.objects.create(
        company=other,
        user=tenant_a.owner,
        role=CompanyUser.Role.ACCOUNTANT,
        can_view_financial_reports=True,
        is_active=True,
    )
    tenant_a.owner.active_company = None
    tenant_a.owner.save(update_fields=["active_company"])
    client = APIClient()
    client.force_authenticate(user=tenant_a.owner)
    resp = client.get("/api/v1/feature-flags/")
    assert resp.status_code == 200, resp.data
    assert "ENABLE_SETUP_WIZARD" in resp.data
    assert "ENABLE_MANUFACTURING" not in resp.data
