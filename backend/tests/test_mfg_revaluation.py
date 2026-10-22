"""QOS-0146: stock on hand re-priced to the standard cost in force (preview, post, reverse)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.invariants import assert_all_invariants
from inventory.models import MovementType, StockBalance
from inventory.services import InventoryService, InventoryValuationService
from manufacturing.models import StandardCost, StandardRevaluation
from manufacturing.services import revaluation
from tests.mfg_helpers import account_net, body, member, prepare, stocked

pytestmark = pytest.mark.django_db

BASE = "/api/v1/manufacturing/standard-revaluations/"


def D(v):
    return Decimal(str(v))


@pytest.fixture(params=["WAVG", "FIFO"])
def method(request):
    return request.param


def stock_value(company, product):
    return sum((D(r["value"]) for r in InventoryValuationService.valuation(company, product=product)), D(0))


def world(tenant, method, *, standard="12", cost="10", qty=100):
    company = prepare(tenant, method=method, costing_gl=True)
    fg = stocked(tenant, "RV-FG", qty, cost)
    StandardCost.objects.create(
        company=company, product=fg, effective_from=timezone.localdate() - timedelta(days=1), material=D(standard),
    )
    return company, fg


def test_preview_lists_the_change_and_moves_nothing(tenant_a, method):
    company, fg = world(tenant_a, method)
    run = revaluation.preview(company, tenant_a.owner)
    line = run.lines.get()
    assert run.status == "DRAFT" and run.number == ""
    assert (D(line.old_unit_cost), D(line.new_unit_cost), D(line.qty)) == (D("10"), D("12"), D("100"))
    assert run.total_before == D("1000.00") and run.total_after == D("1200.00") and run.total_change == D("200.00")
    assert stock_value(company, fg) == D("1000.00")
    assert StockBalance.objects.get(company=company, product=fg).on_hand == D(100)


def test_posting_reprices_stock_and_books_the_difference(tenant_a, method):
    company, fg = world(tenant_a, method)
    inventory_before = account_net(company, "1400")
    run = revaluation.post(revaluation.preview(company, tenant_a.owner), tenant_a.owner)
    assert run.status == "POSTED" and run.number.startswith("SR-")
    assert StockBalance.objects.get(company=company, product=fg).on_hand == D(100)
    assert stock_value(company, fg) == D("1200.00")
    assert InventoryService.available_quantity(company, fg) == D(100)
    assert account_net(company, "1400") - inventory_before == D("200.00")
    assert account_net(company, "5420") == D("-200.00")
    assert_all_invariants(company)
    # Issuing the stock now takes it out at the standard.
    out = InventoryService.post_movement(
        company=company, product=fg, movement_type=MovementType.SALE, quantity=D(10), user=tenant_a.owner,
        reference_type="test", reference_id="1",
    )
    assert D(out.unit_cost) == D("12.0000")


def test_a_lower_standard_writes_the_stock_down(tenant_a, method):
    company, fg = world(tenant_a, method, standard="8")
    run = revaluation.post(revaluation.preview(company, tenant_a.owner), tenant_a.owner)
    assert run.total_change == D("-200.00") and stock_value(company, fg) == D("800.00")
    assert account_net(company, "5420") == D("200.00")
    assert_all_invariants(company)


def test_fifo_layers_of_different_cost_are_all_repriced(tenant_a):
    company, fg = world(tenant_a, "FIFO", standard="13", cost="10", qty=50)
    InventoryService.post_movement(
        company=company, product=fg, movement_type=MovementType.PURCHASE, quantity=D(50), unit_cost=D("14"),
        user=tenant_a.owner, reference_type="test", reference_id="2",
    )
    run = revaluation.preview(company, tenant_a.owner)
    assert run.total_before == D("1200.00")                   # 50 at 10 and 50 at 14
    revaluation.post(run, tenant_a.owner)
    assert stock_value(company, fg) == D("1300.00")           # 100 at 13
    assert_all_invariants(company)


def test_a_lot_already_at_the_standard_is_left_alone(tenant_a, method):
    company, fg = world(tenant_a, method, standard="10")
    with pytest.raises(Exception) as err:
        revaluation.post(revaluation.preview(company, tenant_a.owner), tenant_a.owner)
    assert err.value.detail.code == "MFG_REVAL_NOTHING"


def test_reversal_puts_the_old_cost_back(tenant_a, method):
    company, fg = world(tenant_a, method)
    inventory_before = account_net(company, "1400")
    run = revaluation.post(revaluation.preview(company, tenant_a.owner), tenant_a.owner)
    undone = revaluation.reverse(run, tenant_a.owner, "wrong standard")
    assert undone.status == "REVERSED" and undone.reverse_reason == "wrong standard"
    assert stock_value(company, fg) == D("1000.00")
    assert account_net(company, "1400") == inventory_before and account_net(company, "5420") == 0
    assert_all_invariants(company)


def test_reversal_is_refused_once_the_stock_has_moved(tenant_a, method):
    company, fg = world(tenant_a, method)
    run = revaluation.post(revaluation.preview(company, tenant_a.owner), tenant_a.owner)
    InventoryService.post_movement(
        company=company, product=fg, movement_type=MovementType.SALE, quantity=D(5), user=tenant_a.owner,
        reference_type="test", reference_id="3",
    )
    with pytest.raises(Exception) as err:
        revaluation.reverse(run, tenant_a.owner, "too late")
    assert err.value.detail.code == "MFG_REVAL_MOVED"


def test_a_posted_run_cannot_be_posted_twice_and_a_future_date_is_refused(tenant_a, method):
    company, fg = world(tenant_a, method)
    run = revaluation.post(revaluation.preview(company, tenant_a.owner), tenant_a.owner)
    with pytest.raises(Exception) as err:
        revaluation.post(run, tenant_a.owner)
    assert err.value.detail.code == "MFG_DOC_NOT_DRAFT"
    with pytest.raises(Exception) as err:
        revaluation.preview(company, tenant_a.owner, as_of=timezone.localdate() + timedelta(days=2))
    assert err.value.detail.code == "MFG_REVAL_FUTURE"


def test_one_item_run_needs_a_standard_and_skips_serial_items(tenant_a, method):
    company, fg = world(tenant_a, method)
    other = stocked(tenant_a, "RV-NO", 10, 5)
    with pytest.raises(Exception) as err:
        revaluation.preview(company, tenant_a.owner, product=other)
    assert err.value.detail.code == "MFG_REVAL_NO_STANDARD"
    run = revaluation.preview(company, tenant_a.owner)                       # the whole-company run ignores items with no standard
    assert [ln.product_id for ln in run.lines.all()] == [fg.pk]


def test_api_roles_flag_and_flow(tenant_a):
    company = prepare(tenant_a, costing_gl=False)
    assert tenant_a.client.get(BASE).status_code == 404
    company, fg = world(tenant_a, "WAVG")
    _a, acc = member(tenant_a, "ACCOUNTANT")
    _i, floor = member(tenant_a, "INVENTORY_STAFF", can_manage_inventory=True)
    assert floor.get(BASE).status_code == 403
    assert floor.post(BASE, {}, format="json").status_code == 403
    made = acc.post(BASE, {}, format="json")
    assert made.status_code == 201, made.data
    run = body(made)
    assert run["status"] == "DRAFT" and D(run["total_change"]) == D("200.00") and len(run["lines"]) == 1
    posted = acc.post(f"{BASE}{run['id']}/post/", {}, format="json", HTTP_IDEMPOTENCY_KEY="rv-1")
    assert posted.status_code == 200, posted.data
    assert body(posted)["status"] == "POSTED"
    assert acc.post(f"{BASE}{run['id']}/reverse/", {"reason": "x"}, format="json").status_code == 403   # managers reverse
    rev = tenant_a.client.post(f"{BASE}{run['id']}/reverse/", {"reason": "typo"}, format="json", HTTP_IDEMPOTENCY_KEY="rv-2")
    assert rev.status_code == 200 and body(rev)["status"] == "REVERSED"
    again = acc.post(BASE, {}, format="json")
    assert acc.delete(f"{BASE}{body(again)['id']}/discard/").status_code == 204
    assert StandardRevaluation.objects.filter(company=company).count() == 1


def test_scrap_and_job_worker_stock_is_not_repriced(tenant_a, method):
    from inventory.aux_warehouses import ensure_aux_warehouse

    company, fg = world(tenant_a, method)
    scrap = ensure_aux_warehouse(company, "SCRAP")
    InventoryService.post_movement(
        company=company, product=fg, warehouse=scrap, movement_type=MovementType.PURCHASE, quantity=D(5),
        unit_cost=D("2"), user=tenant_a.owner, reference_type="test", reference_id="9",
    )
    run = revaluation.preview(company, tenant_a.owner)
    assert [ln.warehouse_id for ln in run.lines.all()] == [InventoryService.default_warehouse(company).pk]
    revaluation.post(run, tenant_a.owner)
    assert StockBalance.objects.get(company=company, product=fg, warehouse=scrap).on_hand == D(5)
    assert_all_invariants(company)
