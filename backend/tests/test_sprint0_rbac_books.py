"""Sprint 0 RBAC + tenancy: VIEWER writes, payment/inventory ACL, cross-tenant FKs."""

import pytest
from rest_framework.test import APIClient

from accounts.models import CompanyUser
from inventory.services import InventoryService
from tests.conftest import add_stock, make_product

pytestmark = pytest.mark.django_db


def _body(resp):
    data = resp.data
    if isinstance(data, dict) and isinstance(data.get("data"), (dict, list)):
        return data["data"]
    return data


def _as_viewer(tenant, **caps):
    membership = CompanyUser.objects.get(company=tenant.company, user=tenant.staff)
    membership.role = CompanyUser.Role.VIEWER
    for field, value in (CompanyUser.capability_defaults_for_role(CompanyUser.Role.VIEWER) or {}).items():
        setattr(membership, field, value)
    for field, value in caps.items():
        setattr(membership, field, value)
    membership.save()
    return membership


def test_bom_create_rejects_cross_tenant_product(tenant_a, tenant_b):
    """BB-000672: foreign product PK on BOM create is 400, not a cross-tenant write."""
    other = make_product(tenant_b.company, name="Beta FG", sku="BETA-FG")
    resp = tenant_a.client.post(
        "/api/v1/manufacturing/boms/",
        {"product": other.id, "name": "Leaked BOM", "status": "ACTIVE", "lines": []},
        format="json",
    )
    assert resp.status_code == 400, resp.data


def test_viewer_cannot_create_work_order(tenant_a):
    """BB-000553: VIEWER cannot POST manufacturing work orders."""
    _as_viewer(tenant_a)
    fg = make_product(tenant_a.company, name="FG", sku="S0-FG")
    component = make_product(tenant_a.company, name="Comp", sku="S0-COMP")
    bom = tenant_a.client.post(
        "/api/v1/manufacturing/boms/",
        {
            "product": fg.id,
            "name": "FG BOM",
            "status": "ACTIVE",
            "lines": [{"component": component.id, "qty": "1"}],
        },
        format="json",
    )
    assert bom.status_code == 201, bom.data
    resp = tenant_a.staff_client.post(
        "/api/v1/manufacturing/work-orders/",
        {"bom": _body(bom)["id"], "qty": "1"},
        format="json",
    )
    assert resp.status_code == 403


def test_viewer_cannot_create_pay_run(tenant_a):
    """BB-000553: VIEWER cannot POST payroll pay runs."""
    _as_viewer(tenant_a)
    resp = tenant_a.staff_client.post(
        "/api/v1/payroll/pay-runs/",
        {"period": "2026-04"},
        format="json",
    )
    assert resp.status_code == 403


def test_viewer_cannot_create_lead(tenant_a):
    """BB-000553: VIEWER cannot POST CRM leads."""
    _as_viewer(tenant_a)
    resp = tenant_a.staff_client.post(
        "/api/v1/crm/leads/",
        {"name": "Prospect", "status": "NEW"},
        format="json",
    )
    assert resp.status_code == 403


def test_viewer_with_reports_cannot_list_payments(tenant_a):
    """BB-000691: VIEWER + can_view_financial_reports still cannot list payments."""
    _as_viewer(tenant_a, can_view_financial_reports=True)
    client = APIClient()
    client.force_authenticate(user=tenant_a.staff)
    resp = client.get("/api/v1/payments/receipts/")
    assert resp.status_code == 403


def test_viewer_blocked_from_inventory_cost_and_aa(tenant_a):
    """BB-000618: VIEWER cannot read movements, low-stock, warehouse, or AA lists."""
    _as_viewer(tenant_a, can_view_financial_reports=True)
    product = make_product(tenant_a.company, sku="S0-INV", reorder_level="5")
    add_stock(tenant_a, product, "1")
    warehouse = InventoryService.default_warehouse(tenant_a.company)

    movements = tenant_a.staff_client.get("/api/v1/inventory/movements/")
    assert movements.status_code == 403

    alerts = tenant_a.staff_client.get("/api/v1/inventory/alerts/")
    assert alerts.status_code == 403

    wh = tenant_a.staff_client.get(f"/api/v1/inventory/warehouses/{warehouse.id}/")
    assert wh.status_code == 403

    aa = tenant_a.staff_client.get("/api/v1/banking/aa/")
    assert aa.status_code in (403, 404)
