"""Sprint B: cancel released WO restores stock and reverses WIP 1450."""

from decimal import Decimal

import pytest

from accounting.models import JournalEntry
from accounting.services import seed_chart_of_accounts
from inventory.models import StockBalance
from inventory.services import InventoryService
from tests.conftest import add_stock, make_product

pytestmark = pytest.mark.django_db


def _body(resp):
    data = resp.data
    if isinstance(data, dict) and isinstance(data.get("data"), (dict, list)):
        return data["data"]
    return data


def _account_net(company, code: str) -> Decimal:
    """Net including REVERSED originals + POSTED reversals (pair should cancel)."""
    debit = Decimal("0")
    credit = Decimal("0")
    entries = JournalEntry.objects.filter(
        company=company,
        status__in=[JournalEntry.Status.POSTED, JournalEntry.Status.REVERSED],
    ).prefetch_related("lines__account")
    for entry in entries:
        for jl in entry.lines.all():
            if jl.account.code == code:
                debit += jl.debit
                credit += jl.credit
    return debit - credit


def test_cancel_released_wo_restores_stock_and_reverses_wip(tenant_a):
    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(company, tenant_a.owner)
    fg = make_product(company, sku="SB-FG")
    component = make_product(company, sku="SB-COMP", purchase_price="10")
    add_stock(tenant_a, component, "10", unit_cost="10")
    bom = tenant_a.client.post(
        "/api/v1/manufacturing/boms/",
        {
            "product": fg.id,
            "name": "Cancel WIP BOM",
            "status": "ACTIVE",
            "lines": [{"component": component.id, "qty": "1"}],
        },
        format="json",
    )
    assert bom.status_code == 201, bom.data
    wo = tenant_a.client.post(
        "/api/v1/manufacturing/work-orders/",
        {"bom": _body(bom)["id"], "qty": "4"},
        format="json",
    )
    wo_id = _body(wo)["id"]
    release = tenant_a.client.post(f"/api/v1/manufacturing/work-orders/{wo_id}/release/")
    assert release.status_code == 200, release.data
    wh = InventoryService.default_warehouse(company)
    assert StockBalance.objects.get(company=company, product=component, warehouse=wh).on_hand == Decimal("6")
    assert _account_net(company, "1450") == Decimal("40.00")
    cancel = tenant_a.client.post(f"/api/v1/manufacturing/work-orders/{wo_id}/cancel/")
    assert cancel.status_code == 200, cancel.data
    assert _body(cancel)["status"] == "CANCELLED"
    assert StockBalance.objects.get(company=company, product=component, warehouse=wh).on_hand == Decimal("10")
    release_je = JournalEntry.objects.get(
        company=company, source_type="WORK_ORDER", source_id=wo_id, purpose="RELEASE",
    )
    assert release_je.status == JournalEntry.Status.REVERSED
    assert JournalEntry.objects.filter(
        company=company, source_type="JOURNAL_REVERSAL", source_id=release_je.id, purpose="REVERSE",
        status=JournalEntry.Status.POSTED,
    ).exists()
    assert _account_net(company, "1450") == Decimal("0.00")
