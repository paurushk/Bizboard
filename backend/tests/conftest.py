from decimal import Decimal
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from accounts.models import Company, CompanyUser, User
from django.core.cache import cache
from masters.models import Customer, Product, Supplier


@pytest.fixture(autouse=True)
def clear_cache_before_each_test():
    cache.clear()
    yield
    cache.clear()


def make_tenant(slug, state="Karnataka"):
    owner = User.objects.create_user(
        email=f"owner@{slug}.test", password="StrongPass123!", full_name=f"{slug} owner",
        phone=f"9{abs(hash(slug)) % 10**9:09d}",
    )
    staff = User.objects.create_user(
        email=f"staff@{slug}.test", password="StrongPass123!", full_name=f"{slug} staff",
    )
    company = Company.objects.create(name=f"{slug} Traders", state=state, ai_features_enabled=True)
    CompanyUser.objects.create(
        company=company, user=owner, role=CompanyUser.Role.OWNER,
        can_manage_inventory=True, can_import=True,
    )
    CompanyUser.objects.create(
        company=company, user=staff, role=CompanyUser.Role.SALES_STAFF,
    )
    client = APIClient()
    client.force_authenticate(user=owner)
    staff_client = APIClient()
    staff_client.force_authenticate(user=staff)
    return SimpleNamespace(
        company=company, owner=owner, staff=staff, client=client, staff_client=staff_client
    )


def make_product(company, name="Widget", sku="WID-1", gst_rate="18",
                 purchase_price="80", selling_price="100", reorder_level="0", **kwargs):
    return Product.objects.create(
        company=company, name=name, sku=sku, gst_rate=Decimal(gst_rate),
        purchase_price=Decimal(purchase_price), selling_price=Decimal(selling_price),
        reorder_level=Decimal(reorder_level), **kwargs,
    )


def make_customer(company, name="Ravi Kumar", state="Karnataka", **kwargs):
    return Customer.objects.create(company=company, name=name, state=state, **kwargs)


def make_supplier(company, name="Mega Suppliers", state="Karnataka", **kwargs):
    return Supplier.objects.create(company=company, name=name, state=state, **kwargs)


@pytest.fixture
def tenant_a(db):
    return make_tenant("alpha", state="Karnataka")


@pytest.fixture
def tenant_b(db):
    return make_tenant("beta", state="Maharashtra")


def add_stock(tenant, product, qty, unit_cost="80"):
    from inventory.models import MovementType
    from inventory.services import InventoryService

    return InventoryService.post_movement(
        company=tenant.company, product=product,
        movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal(qty), unit_cost=Decimal(unit_cost), user=tenant.owner,
    )


def create_draft_invoice(tenant, customer, items, invoice_type="GST"):
    payload = {
        "customer": customer.id,
        "invoice_type": invoice_type,
        "items": items,
    }
    resp = tenant.client.post("/api/v1/sales/invoices/", payload, format="json")
    assert resp.status_code == 201, resp.data
    return resp.data


def create_draft_purchase(tenant, supplier, items, purchase_type="GST"):
    payload = {
        "supplier": supplier.id,
        "purchase_type": purchase_type,
        "items": items,
    }
    resp = tenant.client.post("/api/v1/purchases/invoices/", payload, format="json")
    assert resp.status_code == 201, resp.data
    return resp.data
