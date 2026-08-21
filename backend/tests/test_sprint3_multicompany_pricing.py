"""Sprint 3: consent invite, X-Company-Id 409, server price lists."""

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import CompanyUser
from masters.models import PriceList, PriceListItem
from sales.models import SalesInvoice
from tests.conftest import add_stock, make_customer, make_product

pytestmark = pytest.mark.django_db


def test_bb_000673_existing_user_consent_invite_joins_second_company(tenant_a, tenant_b):
    existing = tenant_b.owner
    resp = tenant_a.client.post(
        "/api/v1/company/users/",
        {"email": existing.email, "role": "SALES_STAFF", "full_name": "Cross Firm"},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    body = resp.data.get("data") or resp.data
    assert body.get("consent_required") is True
    token = body["invite_token"]
    membership = CompanyUser.objects.get(company=tenant_a.company, user=existing)
    assert membership.is_active is False

    guest = APIClient()
    accepted = guest.post(
        "/api/v1/auth/invite/accept/",
        {"token": token},
        format="json",
    )
    assert accepted.status_code == 200, accepted.data
    membership.refresh_from_db()
    assert membership.is_active is True

    client = APIClient()
    client.force_authenticate(user=existing)
    existing.active_company_id = tenant_b.company.id
    existing.save(update_fields=["active_company_id"])
    switched = client.post(
        "/api/v1/auth/switch-company/",
        {"company_id": tenant_a.company.id},
        format="json",
    )
    assert switched.status_code == 200, switched.data
    existing.refresh_from_db()
    assert existing.active_company_id == tenant_a.company.id


def test_bb_000658_stale_x_company_id_returns_409(tenant_a, tenant_b):
    user = tenant_a.owner
    CompanyUser.objects.create(
        company=tenant_b.company,
        user=user,
        role=CompanyUser.Role.OWNER,
        can_create_sales=True,
    )
    user.active_company_id = tenant_a.company.id
    user.save(update_fields=["active_company_id"])
    client = APIClient()
    client.force_authenticate(user=user)
    client.credentials(HTTP_X_COMPANY_ID=str(tenant_b.company.id))
    resp = client.get("/api/v1/auth/me/")
    assert resp.status_code == 409


def test_bb_000657_server_resolves_price_list(tenant_a):
    product = make_product(tenant_a.company, selling_price="100")
    add_stock(tenant_a, product, "5")
    price_list = PriceList.objects.create(company=tenant_a.company, name="Contract")
    PriceListItem.objects.create(
        company=tenant_a.company, price_list=price_list, product=product, unit_price=Decimal("90.00"),
    )
    customer = make_customer(tenant_a.company)
    customer.price_list = price_list
    customer.save(update_fields=["price_list"])
    created = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": customer.id,
            "invoice_type": "NON_GST",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "10"}],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    inv_id = (created.data.get("data") or created.data)["id"]
    invoice = SalesInvoice.objects.get(pk=inv_id)
    line = invoice.items.get()
    assert line.unit_price == Decimal("90.00")
