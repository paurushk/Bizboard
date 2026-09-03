"""Wave 17D ERP mega MVP smoke tests — manufacturing, payroll, CRM, Tally HTTP."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from accounting.models import JournalEntry
from crm.models import Lead, Opportunity
from inventory.models import StockBalance
from inventory.services import InventoryService
from payroll.models import Employee
from tests.conftest import add_stock, make_product

pytestmark = pytest.mark.django_db


def _body(resp):
    return resp.data.get("data", resp.data)


def test_bom_work_order_release_complete(tenant_a):
    company = tenant_a.company
    fg = make_product(company, name="Finished Good", sku="FG-1", purchase_price="50")
    component = make_product(company, name="Component", sku="COMP-1", purchase_price="10")
    add_stock(tenant_a, component, "20")

    bom_resp = tenant_a.client.post(
        "/api/v1/manufacturing/boms/",
        {
            "product": fg.id,
            "name": "FG BOM",
            "status": "ACTIVE",
            "lines": [{"component": component.id, "qty": "2"}],
        },
        format="json",
    )
    assert bom_resp.status_code == 201, bom_resp.data
    bom_id = _body(bom_resp)["id"]

    wo_resp = tenant_a.client.post(
        "/api/v1/manufacturing/work-orders/",
        {"bom": bom_id, "qty": "3"},
        format="json",
    )
    assert wo_resp.status_code == 201, wo_resp.data
    wo_id = _body(wo_resp)["id"]

    release = tenant_a.client.post(f"/api/v1/manufacturing/work-orders/{wo_id}/release/")
    assert release.status_code == 200, release.data
    assert _body(release)["status"] == "RELEASED"

    wh = InventoryService.default_warehouse(company)
    comp_bal = StockBalance.objects.get(company=company, product=component, warehouse=wh)
    assert comp_bal.on_hand == Decimal("14")  # 20 - (2 * 3)

    complete = tenant_a.client.post(f"/api/v1/manufacturing/work-orders/{wo_id}/complete/")
    assert complete.status_code == 200, complete.data
    assert _body(complete)["status"] == "COMPLETED"

    fg_bal = StockBalance.objects.get(company=company, product=fg, warehouse=wh)
    assert fg_bal.on_hand == Decimal("3")


@override_settings(ENABLE_MANUFACTURING=False)
def test_manufacturing_disabled_returns_404(tenant_a):
    resp = tenant_a.client.get("/api/v1/manufacturing/boms/")
    assert resp.status_code == 404


def test_payrun_complete(tenant_a):
    emp = Employee.objects.create(
        company=tenant_a.company,
        name="Alice",
        code="E001",
        salary=Decimal("50000"),
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    run_resp = tenant_a.client.post(
        "/api/v1/payroll/pay-runs/",
        {"period": "2026-04"},
        format="json",
    )
    assert run_resp.status_code == 201, run_resp.data
    run_id = _body(run_resp)["id"]

    complete = tenant_a.client.post(f"/api/v1/payroll/pay-runs/{run_id}/complete/")
    assert complete.status_code == 200, complete.data
    body = _body(complete)
    assert body["status"] == "COMPLETED"
    assert len(body["slips"]) == 1
    # Default KA PT slab: gross 50000 → PT 200; PF/ESI off.
    assert Decimal(str(body["slips"][0]["pt_amount"])) == Decimal("200.00")
    assert Decimal(str(body["slips"][0]["net"])) == emp.salary - Decimal("200.00")


def test_payrun_complete_posts_journal_when_accounting_enabled(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    Employee.objects.create(
        company=tenant_a.company,
        name="Bob",
        code="E002",
        salary=Decimal("30000"),
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    run_resp = tenant_a.client.post(
        "/api/v1/payroll/pay-runs/",
        {"period": "2026-05"},
        format="json",
    )
    run_id = _body(run_resp)["id"]
    complete = tenant_a.client.post(f"/api/v1/payroll/pay-runs/{run_id}/complete/")
    assert complete.status_code == 200, complete.data
    assert JournalEntry.objects.filter(
        company=tenant_a.company, source_type="PAY_RUN", source_id=run_id,
    ).exists()


def test_crm_lead_opportunity_crud(tenant_a):
    lead_resp = tenant_a.client.post(
        "/api/v1/crm/leads/",
        {"name": "Prospect Co", "phone": "9876543210", "email": "p@example.com", "status": "NEW"},
        format="json",
    )
    assert lead_resp.status_code == 201, lead_resp.data
    lead_id = _body(lead_resp)["id"]

    patch = tenant_a.client.patch(
        f"/api/v1/crm/leads/{lead_id}/",
        {"status": "QUALIFIED"},
        format="json",
    )
    assert patch.status_code == 200, patch.data
    assert Lead.objects.get(pk=lead_id).status == Lead.Status.QUALIFIED

    opp_resp = tenant_a.client.post(
        "/api/v1/crm/opportunities/",
        {"lead": lead_id, "title": "Q2 Deal", "amount": "150000", "stage": "OPEN"},
        format="json",
    )
    assert opp_resp.status_code == 201, opp_resp.data
    opp_id = _body(opp_resp)["id"]

    listing = tenant_a.client.get("/api/v1/crm/opportunities/")
    assert listing.status_code == 200, listing.data
    results = _body(listing)
    if isinstance(results, dict) and "results" in results:
        ids = [r["id"] for r in results["results"]]
    else:
        ids = [r["id"] for r in results]
    assert opp_id in ids

    won = tenant_a.client.patch(
        f"/api/v1/crm/opportunities/{opp_id}/",
        {"stage": "WON"},
        format="json",
    )
    assert won.status_code == 200, won.data
    assert Opportunity.objects.get(pk=opp_id).stage == Opportunity.Stage.WON


@patch("requests.post")
def test_tally_http_push_masters(mock_post, tenant_a):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.ok = True
    mock_resp.text = "<RESPONSE>Success</RESPONSE>"
    mock_post.return_value = mock_resp

    from integrations.tally.adapter import push_masters_http

    result = push_masters_http(tenant_a.company, "http://localhost:9000")
    assert result["ok"] is True
    assert result["kind"] == "masters"
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "http://localhost:9000"
    payload = kwargs.get("data") or (args[1] if len(args) > 1 else b"")
    assert b"<ENVELOPE>" in payload


@patch("requests.post")
def test_tally_http_push_via_api(mock_post, tenant_a):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.ok = True
    mock_resp.text = "OK"
    mock_post.return_value = mock_resp

    resp = tenant_a.client.post(
        "/api/v1/integrations/tally/push-http/",
        {"kind": "masters", "baseUrl": "http://tally.test:9000"},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    body = _body(resp)
    assert body["ok"] is True
    mock_post.assert_called_once()
