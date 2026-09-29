"""J-PROJ-P1-MILESTONE. Two ready milestones become two draft service invoices."""

import pytest

from core.invariants import assert_all_invariants
from masters.models import Product
from sales.models import SalesInvoice
from tests.conftest import make_customer, make_product

pytestmark = pytest.mark.django_db


def test_j_proj_p1_milestone_invoices_services_and_blocks_close(tenant_a):
    """J-PROJ-P1-MILESTONE."""
    assert tenant_a.client.get("/api/v1/projects/").status_code == 404
    tenant_a.company.feature_flags = {"ENABLE_PROJECTS": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    customer = make_customer(tenant_a.company)
    service = make_product(tenant_a.company, name="Civil", sku="CV-P", product_type=Product.ProductType.SERVICE)
    goods = make_product(tenant_a.company, name="Cement", sku="CM-P")
    created = tenant_a.client.post("/api/v1/projects/", {"customer": customer.id, "name": "Site"}, format="json")
    assert created.status_code == 201, created.data
    pid = created.data["id"]
    assert tenant_a.client.post(
        f"/api/v1/projects/{pid}/milestones/",
        {"name": "Cement", "amount": "1000", "service_product": goods.id, "sequence": 1},
        format="json",
    ).status_code == 400
    for seq, name in ((1, "Foundation"), (2, "Handover")):
        row = tenant_a.client.post(
            f"/api/v1/projects/{pid}/milestones/",
            {"name": name, "amount": "1000", "service_product": service.id, "sequence": seq},
            format="json",
        )
        assert row.status_code == 200, row.data
    detail = tenant_a.client.get(f"/api/v1/projects/{pid}/")
    ids = [m["id"] for m in detail.data["milestones"]]
    tenant_a.client.post(f"/api/v1/projects/{pid}/milestones/{ids[0]}/ready/")
    blocked = tenant_a.client.post(f"/api/v1/projects/{pid}/close/")
    assert blocked.status_code == 400
    tenant_a.client.post(f"/api/v1/projects/{pid}/milestones/{ids[1]}/ready/")
    first = tenant_a.client.post(f"/api/v1/projects/{pid}/milestones/{ids[0]}/invoice/")
    second = tenant_a.client.post(f"/api/v1/projects/{pid}/milestones/{ids[1]}/invoice/")
    assert first.data["milestones"][0]["sales_invoice"] != second.data["milestones"][1]["sales_invoice"]
    assert SalesInvoice.objects.filter(company=tenant_a.company).count() == 2
    draft_close = tenant_a.client.post(f"/api/v1/projects/{pid}/close/")
    assert draft_close.status_code == 400
    SalesInvoice.objects.filter(company=tenant_a.company).update(status=SalesInvoice.Status.COMPLETED)
    closed = tenant_a.client.post(f"/api/v1/projects/{pid}/close/")
    assert closed.status_code == 200, closed.data
    assert closed.data["status"] == "CLOSED"
    assert_all_invariants(tenant_a.company)
