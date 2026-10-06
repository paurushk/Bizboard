"""J-JOB-P9-REPAIR. A job becomes one draft invoice. Stock and GST post when that invoice completes."""

from rest_framework.test import APIClient

from accounts.models import CompanyUser, User
from core.invariants import assert_all_invariants
from inventory.models import StockMovement
from masters.models import Product
from sales.models import SalesInvoice
from sales.services import SalesService
from tests.conftest import add_stock, make_customer, make_product

import pytest

pytestmark = pytest.mark.django_db


def test_j_job_p9_repair_converts_once_then_posts_stock(tenant_a):
    """J-JOB-P9-REPAIR."""
    hidden = tenant_a.client.get("/api/v1/workshop/job-cards/")
    assert hidden.status_code == 404
    tenant_a.company.feature_flags = {"ENABLE_WORKSHOP": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    customer = make_customer(tenant_a.company)
    part = make_product(tenant_a.company, name="Spare", sku="SP-J", product_type=Product.ProductType.GOODS)
    labour = make_product(
        tenant_a.company, name="Labour", sku="LB-J", product_type=Product.ProductType.SERVICE, gst_rate="18",
    )
    created = tenant_a.client.post(
        "/api/v1/workshop/job-cards/",
        {"customer": customer.id, "complaint": "Motor noise"},
        format="json",
    )
    assert created.status_code == 201, created.data
    job_id = created.data["id"]
    assert tenant_a.client.post(
        f"/api/v1/workshop/job-cards/{job_id}/lines/",
        {"kind": "LABOUR", "product": part.id, "quantity": "1", "unit_price": "100"},
        format="json",
    ).status_code == 400
    assert tenant_a.client.post(
        f"/api/v1/workshop/job-cards/{job_id}/lines/",
        {"kind": "PART", "product": labour.id, "quantity": "1", "unit_price": "100"},
        format="json",
    ).status_code == 400
    # a part line holds its stock (BUG-WRK-002), so the part must be on the shelf first
    add_stock(tenant_a, part, "5")
    assert tenant_a.client.post(
        f"/api/v1/workshop/job-cards/{job_id}/lines/",
        {"kind": "PART", "product": part.id, "quantity": "1", "unit_price": "100"},
        format="json",
    ).status_code == 200
    assert tenant_a.client.post(
        f"/api/v1/workshop/job-cards/{job_id}/lines/",
        {"kind": "LABOUR", "product": labour.id, "quantity": "1", "unit_price": "200"},
        format="json",
    ).status_code == 200
    before = StockMovement.objects.filter(company=tenant_a.company).count()
    converted = tenant_a.client.post(f"/api/v1/workshop/job-cards/{job_id}/convert/")
    assert converted.status_code == 200, converted.data
    invoice_id = converted.data["sales_invoice"]
    again = tenant_a.client.post(f"/api/v1/workshop/job-cards/{job_id}/convert/")
    assert again.data["sales_invoice"] == invoice_id
    assert StockMovement.objects.filter(company=tenant_a.company).count() == before
    SalesService.complete(SalesInvoice.objects.get(pk=invoice_id), tenant_a.owner)
    assert StockMovement.objects.filter(company=tenant_a.company, product=part, quantity__lt=0).exists()
    assert tenant_a.client.post(f"/api/v1/workshop/job-cards/{job_id}/cancel/").status_code == 400
    desk = User.objects.create_user(email="desk-job@x.test", password="StrongPass123!", full_name="Desk")
    CompanyUser.objects.create(
        company=tenant_a.company, user=desk, role=CompanyUser.Role.POLICY_DESK, can_manage_policies=True,
    )
    client = APIClient()
    client.force_authenticate(user=desk)
    assert client.post("/api/v1/workshop/job-cards/", {"customer": customer.id}, format="json").status_code == 403
    assert_all_invariants(tenant_a.company)
