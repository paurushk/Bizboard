"""Open items from the sales invoice review: product cost visibility, profit warnings, relink."""

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from accounts.models import CompanyUser, User
from masters.models import Product
from sales.models import InvoicePublicLink
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _member(tenant, *, role, suffix, **flags):
    user = User.objects.create_user(
        email=f"{role.lower()}-{suffix}@{tenant.company.id}.test",
        password="StrongPass123!",
        full_name=f"{role.title()} {suffix}",
    )
    CompanyUser.objects.create(company=tenant.company, user=user, role=role, **flags)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_sales_only_user_does_not_see_item_cost_but_owner_and_buyer_do(tenant_a):
    product = make_product(tenant_a.company, sku="COST-1", hsn_code="3004", gst_rate="18")
    Product.objects.filter(pk=product.pk).update(purchase_price="40.00")
    seller = _member(tenant_a, role=CompanyUser.Role.SALES_STAFF, suffix="cost-s", can_create_sales=True)
    buyer = _member(tenant_a, role=CompanyUser.Role.MANAGER, suffix="cost-b", can_create_purchases=True)

    assert seller.get(f"/api/v1/products/{product.pk}/").data.get("purchase_price") is None
    assert str(buyer.get(f"/api/v1/products/{product.pk}/").data["purchase_price"]) == "40.00"
    assert str(tenant_a.client.get(f"/api/v1/products/{product.pk}/").data["purchase_price"]) == "40.00"


def test_masked_client_cannot_overwrite_item_cost(tenant_a):
    product = make_product(tenant_a.company, sku="COST-2", hsn_code="3004", gst_rate="18")
    Product.objects.filter(pk=product.pk).update(purchase_price="55.00")
    editor = _member(
        tenant_a, role=CompanyUser.Role.SALES_STAFF, suffix="cost-e",
        can_create_sales=True, can_manage_inventory=False,
    )
    res = editor.patch(f"/api/v1/products/{product.pk}/", {"purchase_price": None, "name": "Renamed"}, format="json")
    # Either the edit is refused for this role, or it ran without touching cost.
    assert res.status_code in (200, 403), res.data
    assert str(Product.objects.get(pk=product.pk).purchase_price) == "55.00"


def test_draft_profit_warns_when_a_stocked_line_has_no_cost(tenant_a):
    product = make_product(tenant_a.company, sku="COST-3", hsn_code="3004", gst_rate="18")
    customer = make_customer(tenant_a.company, name="Cost Buyer", state="Karnataka")
    draft = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "2", "unit_price": "100", "gst_rate": "18"},
    ])
    res = tenant_a.client.get(f"/api/v1/sales/invoices/{draft['id']}/profit-details/")
    assert res.status_code == 200, res.data
    assert res.data["estimated"] is True
    assert res.data["cost_incomplete"] is True
    assert res.data["lines"][0]["cost_missing"] is True


@override_settings(FRONTEND_URL="http://front.test")
def test_revoke_then_share_gives_a_new_url(tenant_a):
    product = make_product(tenant_a.company, sku="RELINK-1", hsn_code="3004", gst_rate="18")
    add_stock(tenant_a, product, "3")
    customer = make_customer(tenant_a.company, name="Relink Buyer", state="Karnataka")
    draft = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"},
    ])
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/").status_code == 200
    share = lambda: tenant_a.client.post(  # noqa: E731
        f"/api/v1/sales/invoices/{draft['id']}/share/",
        {"channel": "WHATSAPP", "recipient": ""}, format="json",
    )
    first = share()
    again = share()
    assert first.data["document_url"] == again.data["document_url"]
    token = first.data["document_url"].rsplit("/", 1)[-1]

    assert tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/public-link/revoke/").status_code == 200
    assert APIClient().get(f"/api/v1/public/invoices/{token}/").status_code == 404

    renewed = share()
    assert renewed.data["document_url"] != first.data["document_url"]
    new_token = renewed.data["document_url"].rsplit("/", 1)[-1]
    assert APIClient().get(f"/api/v1/public/invoices/{new_token}/").status_code == 200
    assert InvoicePublicLink.objects.filter(invoice_id=draft["id"], revoked_at__isnull=True).count() == 1


def test_cached_catalog_list_never_mixes_cost_between_roles(tenant_a):
    product = make_product(tenant_a.company, sku="COST-LIST", hsn_code="3004", gst_rate="18")
    Product.objects.filter(pk=product.pk).update(purchase_price="12.00")
    seller = _member(tenant_a, role=CompanyUser.Role.SALES_STAFF, suffix="list-s", can_create_sales=True)

    def row(client):
        data = client.get("/api/v1/products/").data
        rows = data["results"] if isinstance(data, dict) and "results" in data else data
        return next(r for r in rows if r["sku"] == "COST-LIST")

    # Seller first, so a shared cache would hand the masked rows to the owner.
    assert row(seller).get("purchase_price") is None
    assert str(row(tenant_a.client)["purchase_price"]) == "12.00"
    assert row(seller).get("purchase_price") is None
