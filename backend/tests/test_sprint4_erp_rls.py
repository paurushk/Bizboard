"""Sprint 4: manufacturing cheap fixes, payroll immutability, CRM/RLS honesty."""

import inspect
from decimal import Decimal

import pytest
from django.conf import settings
from django.test import override_settings

from accounting.models import JournalEntry
from core.rls import set_rls_company
from inventory.models import MovementType, StockBalance, StockMovement
from inventory.services import InventoryService
from payroll.models import Employee, PayRun
from tests.conftest import add_stock, make_product

pytestmark = pytest.mark.django_db


def _body(resp):
    data = resp.data
    if isinstance(data, dict) and isinstance(data.get("data"), (dict, list)):
        return data["data"]
    return data


def test_bb_000554_wo_release_uses_manufacture_issue(tenant_a):
    company = tenant_a.company
    fg = make_product(company, name="FG", sku="S4-FG", purchase_price="50")
    component = make_product(company, name="Comp", sku="S4-COMP", purchase_price="10")
    add_stock(tenant_a, component, "20")
    bom = tenant_a.client.post(
        "/api/v1/manufacturing/boms/",
        {
            "product": fg.id,
            "name": "FG BOM",
            "status": "ACTIVE",
            "lines": [{"component": component.id, "qty": "2"}],
        },
        format="json",
    )
    assert bom.status_code == 201, bom.data
    wo = tenant_a.client.post(
        "/api/v1/manufacturing/work-orders/",
        {"bom": _body(bom)["id"], "qty": "3"},
        format="json",
    )
    assert wo.status_code == 201, wo.data
    wo_id = _body(wo)["id"]
    release = tenant_a.client.post(f"/api/v1/manufacturing/work-orders/{wo_id}/release/")
    assert release.status_code == 200, release.data
    moves = StockMovement.objects.filter(
        company=company, reference_type="work_order", reference_id=str(wo_id),
    )
    assert moves.filter(movement_type=MovementType.MANUFACTURE_ISSUE).exists()
    assert not moves.filter(movement_type=MovementType.SALE).exists()


def test_bb_000681_archived_bom_cannot_release(tenant_a):
    fg = make_product(tenant_a.company, sku="S4-FG2")
    component = make_product(tenant_a.company, sku="S4-COMP2")
    add_stock(tenant_a, component, "10")
    bom = tenant_a.client.post(
        "/api/v1/manufacturing/boms/",
        {
            "product": fg.id,
            "name": "Archived BOM",
            "status": "ARCHIVED",
            "lines": [{"component": component.id, "qty": "1"}],
        },
        format="json",
    )
    wo = tenant_a.client.post(
        "/api/v1/manufacturing/work-orders/",
        {"bom": _body(bom)["id"], "qty": "1"},
        format="json",
    )
    release = tenant_a.client.post(
        f"/api/v1/manufacturing/work-orders/{_body(wo)['id']}/release/",
    )
    assert release.status_code == 400
    assert "ACTIVE" in str(release.data)


def test_bb_000565_cancel_released_wo_restores_stock(tenant_a):
    company = tenant_a.company
    fg = make_product(company, sku="S4-FG3")
    component = make_product(company, sku="S4-COMP3")
    add_stock(tenant_a, component, "10")
    bom = tenant_a.client.post(
        "/api/v1/manufacturing/boms/",
        {
            "product": fg.id,
            "name": "Cancel BOM",
            "status": "ACTIVE",
            "lines": [{"component": component.id, "qty": "1"}],
        },
        format="json",
    )
    wo = tenant_a.client.post(
        "/api/v1/manufacturing/work-orders/",
        {"bom": _body(bom)["id"], "qty": "4"},
        format="json",
    )
    wo_id = _body(wo)["id"]
    assert tenant_a.client.post(f"/api/v1/manufacturing/work-orders/{wo_id}/release/").status_code == 200
    wh = InventoryService.default_warehouse(company)
    assert StockBalance.objects.get(company=company, product=component, warehouse=wh).on_hand == Decimal("6")
    cancel = tenant_a.client.post(f"/api/v1/manufacturing/work-orders/{wo_id}/cancel/")
    assert cancel.status_code == 200, cancel.data
    assert _body(cancel)["status"] == "CANCELLED"
    assert StockBalance.objects.get(company=company, product=component, warehouse=wh).on_hand == Decimal("10")


def test_bb_000682_completed_payrun_immutable(tenant_a):
    Employee.objects.create(
        company=tenant_a.company, name="Pat", code="S4E1", salary=Decimal("1000"),
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    created = tenant_a.client.post("/api/v1/payroll/pay-runs/", {"period": "2026-04"}, format="json")
    run_id = _body(created)["id"]
    assert tenant_a.client.post(f"/api/v1/payroll/pay-runs/{run_id}/complete/").status_code == 200
    patched = tenant_a.client.patch(
        f"/api/v1/payroll/pay-runs/{run_id}/", {"period": "2026-05"}, format="json",
    )
    assert patched.status_code == 400
    deleted = tenant_a.client.delete(f"/api/v1/payroll/pay-runs/{run_id}/")
    assert deleted.status_code == 400
    assert PayRun.objects.filter(pk=run_id, status=PayRun.Status.COMPLETED).exists()


def test_bb_000685_payrun_complete_is_idempotent(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    Employee.objects.create(
        company=tenant_a.company, name="Pat", code="S4E2", salary=Decimal("2000"),
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    created = tenant_a.client.post("/api/v1/payroll/pay-runs/", {"period": "2026-06"}, format="json")
    run_id = _body(created)["id"]
    first = tenant_a.client.post(f"/api/v1/payroll/pay-runs/{run_id}/complete/")
    second = tenant_a.client.post(f"/api/v1/payroll/pay-runs/{run_id}/complete/")
    assert first.status_code == 200
    assert second.status_code == 400
    assert JournalEntry.objects.filter(
        company=tenant_a.company, source_type="PayRun", source_id=run_id, purpose="PAYROLL",
    ).count() == 1


def test_bb_000684_period_and_salary_validated(tenant_a):
    bad_period = tenant_a.client.post("/api/v1/payroll/pay-runs/", {"period": "2026-13"}, format="json")
    assert bad_period.status_code == 400
    bad_salary = tenant_a.client.post(
        "/api/v1/payroll/employees/",
        {"name": "Neg", "code": "NEG1", "salary": "-10", "status": "ACTIVE"},
        format="json",
    )
    assert bad_salary.status_code == 400


def test_bb_000683_payroll_journal_dated_period_month_end(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    Employee.objects.create(
        company=tenant_a.company, name="Pat", code="S4E3", salary=Decimal("3000"),
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    created = tenant_a.client.post("/api/v1/payroll/pay-runs/", {"period": "2026-02"}, format="json")
    run_id = _body(created)["id"]
    assert tenant_a.client.post(f"/api/v1/payroll/pay-runs/{run_id}/complete/").status_code == 200
    entry = JournalEntry.objects.get(
        company=tenant_a.company, source_type="PayRun", source_id=run_id, purpose="PAYROLL",
    )
    assert str(entry.entry_date) == "2026-02-28"


def test_cancel_pay_run_reverses_journal_and_reopens_draft(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    Employee.objects.create(
        company=tenant_a.company, name="Pat", code="S4E4", salary=Decimal("4000"),
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    created = tenant_a.client.post("/api/v1/payroll/pay-runs/", {"period": "2026-03"}, format="json")
    run_id = _body(created)["id"]
    assert tenant_a.client.post(f"/api/v1/payroll/pay-runs/{run_id}/complete/").status_code == 200
    cancel_resp = tenant_a.client.post(f"/api/v1/payroll/pay-runs/{run_id}/cancel/")
    assert cancel_resp.status_code == 200, cancel_resp.data
    assert _body(cancel_resp)["status"] == "DRAFT"
    # Check that original journal is marked REVERSED or a reversal entry was posted
    entry = JournalEntry.objects.get(
        company=tenant_a.company, source_type="PayRun", source_id=run_id, purpose="PAYROLL",
    )
    assert entry.status == JournalEntry.Status.REVERSED


@override_settings(ENABLE_CRM=False)
def test_bb_000582_crm_404_when_flag_off(tenant_a):
    resp = tenant_a.client.get("/api/v1/crm/leads/")
    assert resp.status_code == 404


def test_bb_000551_rls_uses_session_not_local():
    source = inspect.getsource(set_rls_company)
    assert "set_config('app.company_id', %s, false)" in source
    assert "set_config('app.company_id', %s, true)" not in source


def test_bb_000552_rls_stays_disabled_by_default():
    assert getattr(settings, "POSTGRES_RLS_ENABLED", True) is False
