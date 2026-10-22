"""Manufacturing phase 1: issue / return / receipt documents, costing, reversals, close."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.exceptions import BusinessRuleError
from inventory.models import (
    BatchLot, MovementType, StockBalance, StockMovement, StockReservation, Warehouse,
)
from inventory.services import InventoryService
from manufacturing.models import DocumentStatus, WorkOrder
from manufacturing.services import flow, issue as issue_svc, receipt as receipt_svc, release_work_order
from tests.conftest import make_product
from tests.mfg_helpers import account_net, body, make_bom, make_wo, member, prepare, stocked

pytestmark = pytest.mark.django_db


@pytest.fixture(params=["WAVG", "FIFO"])
def method(request):
    return request.param


def D(v):
    return Decimal(str(v))


def setup_order(tenant, method, *, qty=100, per_unit=1, cost=10, stock=1000, outputs=(), **bom_kw):
    """A released work order on the document flow: one component at ₹cost, ``per_unit`` per unit."""
    company = prepare(tenant, method=method, separate=True)
    fg = make_product(company, sku="FG-1", name="Finished")
    comp = stocked(tenant, "COMP-1", stock, cost)
    bom = make_bom(company, fg, [(comp, per_unit)], user=tenant.owner, outputs=outputs, **bom_kw)
    wo = make_wo(company, bom, qty, user=tenant.owner)
    wo = release_work_order(wo, tenant.owner)
    return company, fg, comp, bom, wo


def issue_all(tenant, wo, qty=None):
    wl = wo.component_lines.get()
    lines = [{"wo_line": wl, "qty": qty if qty is not None else wl.qty}]
    doc = issue_svc.create_issue(wo, tenant.owner, lines)
    return issue_svc.post_issue(doc, tenant.owner)


def receive(tenant, wo, good, *, final=False, rejected=0, rework=0, extra=(), **doc):
    lines = [{"kind": "MAIN", "qty_good": good, "qty_rejected": rejected, "qty_rework": rework}, *extra]
    rec = receipt_svc.create_receipt(wo, tenant.owner, {"is_final": final, "lines": lines, **doc})
    return receipt_svc.post_receipt(rec, tenant.owner)


# --- release ----------------------------------------------------------------------------------

def test_release_holds_stock_and_freezes_the_estimate_without_moving_anything(tenant_a, method):
    company, fg, comp, bom, wo = setup_order(tenant_a, method, qty=100, per_unit=2, cost=10)
    assert wo.status == WorkOrder.Status.RELEASED
    assert wo.estimated_unit_cost == D("20.0000")
    assert not StockMovement.objects.filter(reference_type__startswith="mfg").exists()
    bal = StockBalance.objects.get(company=company, product=comp)
    assert bal.on_hand == D(1000) and bal.reserved == D(200)
    hold = StockReservation.objects.get(reference_type="work_order", reference_id=str(wo.pk))
    assert hold.quantity == D(200) and hold.expires_at is None
    # The hold keeps a sale from taking what the order is waiting for.
    assert InventoryService.available_quantity(company, comp) == D(800)


def test_release_holds_only_what_is_available_and_does_not_fail_on_a_shortage(tenant_a, method):
    company, _fg, comp, _bom, wo = setup_order(tenant_a, method, qty=100, per_unit=2, stock=150)
    assert StockBalance.objects.get(company=company, product=comp).reserved == D(150)
    assert wo.status == WorkOrder.Status.RELEASED


# --- issue ------------------------------------------------------------------------------------

def test_partial_issues_move_stock_cost_and_the_books(tenant_a, method):
    company, _fg, comp, _bom, wo = setup_order(tenant_a, method, qty=100, per_unit=1, cost=10)
    first = issue_all(tenant_a, wo, 60)
    wo.refresh_from_db()
    assert first.status == DocumentStatus.POSTED and first.number.startswith("MI-")
    assert wo.status == WorkOrder.Status.IN_PROGRESS
    assert wo.cost_issued == D("600.00")
    line = wo.component_lines.get()
    assert line.qty_issued == D(60) and line.qty_remaining == D(40)
    bal = StockBalance.objects.get(company=company, product=comp)
    assert bal.on_hand == D(940) and bal.reserved == D(40)          # hold shrank as material left
    assert account_net(company, "1450") == D("600.00")
    issue_all(tenant_a, wo, 40)
    wo.refresh_from_db()
    assert wo.cost_issued == D("1000.00") and wo.component_lines.get().qty_remaining == 0
    assert account_net(company, "1450") == D("1000.00")
    assert not StockReservation.objects.filter(reference_type="work_order", released_at__isnull=True).exists()


def test_default_issue_asks_for_everything_still_needed(tenant_a, method):
    _c, _fg, _comp, _bom, wo = setup_order(tenant_a, method, qty=100, per_unit=1)
    issue_all(tenant_a, wo, 30)
    doc = issue_svc.create_issue(wo, tenant_a.owner)
    assert doc.lines.get().qty == D(70)


def test_extra_issue_needs_a_reason_and_a_manager_when_far_over(tenant_a, method):
    _c, _fg, _comp, _bom, wo = setup_order(tenant_a, method, qty=100, per_unit=1)
    wl = wo.component_lines.get()
    over = issue_svc.create_issue(wo, tenant_a.owner, [{"wo_line": wl, "qty": 130}])
    with pytest.raises(BusinessRuleError) as exc:
        issue_svc.post_issue(over, tenant_a.owner)
    assert exc.value.get_codes() == "MFG_EXTRA_NEEDS_REASON"
    over.lines.update(extra_reason="Spillage in the mixer")
    with pytest.raises(BusinessRuleError) as exc:
        issue_svc.post_issue(over, tenant_a.owner, is_manager=False)       # 30 % over, threshold 10 %
    assert exc.value.get_codes() == "MFG_EXTRA_NEEDS_MANAGER"
    posted = issue_svc.post_issue(over, tenant_a.owner, is_manager=True)
    assert posted.lines.get().is_extra
    wo.refresh_from_db()
    assert wo.cost_issued == D("1300.00")


def test_a_small_extra_issue_is_fine_for_inventory_staff(tenant_a, method):
    _c, _fg, _comp, _bom, wo = setup_order(tenant_a, method, qty=100, per_unit=1)
    wl = wo.component_lines.get()
    doc = issue_svc.create_issue(wo, tenant_a.owner, [{"wo_line": wl, "qty": 105, "extra_reason": "Wastage"}])
    issue_svc.post_issue(doc, tenant_a.owner, is_manager=False)


def test_posting_an_issue_twice_posts_once(tenant_a, method):
    _c, _fg, comp, _bom, wo = setup_order(tenant_a, method, qty=10)
    doc = issue_all(tenant_a, wo)
    with pytest.raises(BusinessRuleError) as exc:
        issue_svc.post_issue(doc, tenant_a.owner)
    assert exc.value.get_codes() == "MFG_DOC_NOT_DRAFT"
    assert StockMovement.objects.filter(reference_type="mfg_issue", reference_id=str(doc.pk)).count() == 1


def test_one_step_orders_refuse_documents(tenant_a, method):
    company = prepare(tenant_a, method=method, separate=False)
    fg = make_product(company, sku="OS-FG")
    comp = stocked(tenant_a, "OS-COMP", 50, 5)
    wo = make_wo(company, make_bom(company, fg, [(comp, 1)], user=tenant_a.owner), 5, user=tenant_a.owner)
    release_work_order(wo, tenant_a.owner)
    wo.refresh_from_db()
    with pytest.raises(BusinessRuleError) as exc:
        issue_svc.create_issue(wo, tenant_a.owner)
    assert exc.value.get_codes() == "MFG_LEGACY_MODE"


def test_issue_stops_at_the_period_lock(tenant_a, method):
    from reporting.gst_periods import get_or_create_period
    from reporting.models import GstReturnPeriod

    _c, _fg, _comp, _bom, wo = setup_order(tenant_a, method, qty=10)
    wl = wo.component_lines.get()
    when = timezone.localdate() - timedelta(days=1)
    period = get_or_create_period(tenant_a.company, f"{when.year:04d}-{when.month:02d}")
    period.status = GstReturnPeriod.Status.CLOSED
    period.save()
    doc = issue_svc.create_issue(wo, tenant_a.owner, [{"wo_line": wl, "qty": 5}], doc_date=when)
    with pytest.raises(BusinessRuleError):
        issue_svc.post_issue(doc, tenant_a.owner)


def test_back_dated_issue_needs_a_manager_beyond_the_window(tenant_a, method):
    _c, _fg, _comp, _bom, wo = setup_order(tenant_a, method, qty=10)
    wl = wo.component_lines.get()
    old = timezone.localdate() - timedelta(days=30)
    doc = issue_svc.create_issue(wo, tenant_a.owner, [{"wo_line": wl, "qty": 5}], doc_date=old)
    with pytest.raises(BusinessRuleError) as exc:
        issue_svc.post_issue(doc, tenant_a.owner, can_backdate=False)
    assert exc.value.get_codes() == "MFG_BACKDATE_NEEDS_MANAGER"
    issue_svc.post_issue(doc, tenant_a.owner, can_backdate=True)


def test_future_date_is_refused(tenant_a, method):
    _c, _fg, _comp, _bom, wo = setup_order(tenant_a, method, qty=10)
    wl = wo.component_lines.get()
    doc = issue_svc.create_issue(
        wo, tenant_a.owner, [{"wo_line": wl, "qty": 5}], doc_date=timezone.localdate() + timedelta(days=2),
    )
    with pytest.raises(BusinessRuleError) as exc:
        issue_svc.post_issue(doc, tenant_a.owner)
    assert exc.value.get_codes() == "MFG_FUTURE_DATE"


# --- return -----------------------------------------------------------------------------------

def test_return_puts_material_back_at_the_cost_it_left_at(tenant_a, method):
    company, _fg, comp, _bom, wo = setup_order(tenant_a, method, qty=100, per_unit=1, cost=10)
    issue_all(tenant_a, wo, 100)
    wl = wo.component_lines.get()
    ret = issue_svc.create_return(wo, tenant_a.owner, [{"wo_line": wl, "qty": 25}])
    ret = issue_svc.post_return(ret, tenant_a.owner)
    wo.refresh_from_db()
    assert ret.number.startswith("MR-")
    assert wo.cost_returned == D("250.00") and wo.wip_value == D("750.00")
    assert StockBalance.objects.get(company=company, product=comp).on_hand == D(925)
    assert wo.component_lines.get().qty_returned == D(25)
    assert account_net(company, "1450") == D("750.00")
    # The stock is worth what it was before the order took it.
    assert InventoryService.available_quantity(company, comp) == D(925)
    from inventory.services import InventoryValuationService

    assert InventoryValuationService.unit_cost(company, comp) == D("10")


def test_cannot_return_more_than_is_out(tenant_a, method):
    _c, _fg, _comp, _bom, wo = setup_order(tenant_a, method, qty=100)
    issue_all(tenant_a, wo, 40)
    wl = wo.component_lines.get()
    ret = issue_svc.create_return(wo, tenant_a.owner, [{"wo_line": wl, "qty": 41}])
    with pytest.raises(BusinessRuleError) as exc:
        issue_svc.post_return(ret, tenant_a.owner)
    assert exc.value.get_codes() == "MFG_OVER_RETURN"


def test_return_reverses_cleanly(tenant_a, method):
    company, _fg, comp, _bom, wo = setup_order(tenant_a, method, qty=100)
    issue_all(tenant_a, wo, 100)
    wl = wo.component_lines.get()
    ret = issue_svc.post_return(issue_svc.create_return(wo, tenant_a.owner, [{"wo_line": wl, "qty": 30}]), tenant_a.owner)
    issue_svc.reverse_return(ret, tenant_a.owner, "Counted wrong")
    wo.refresh_from_db()
    assert wo.cost_returned == D("0.00") and wo.component_lines.get().qty_returned == 0
    assert StockBalance.objects.get(company=company, product=comp).on_hand == D(900)
    assert account_net(company, "1450") == D("1000.00")


# --- receipts and cost ------------------------------------------------------------------------

def test_two_receipts_cost_the_whole_pool_exactly(tenant_a, method):
    company, fg, _comp, _bom, wo = setup_order(tenant_a, method, qty=100, per_unit=1, cost=10)
    issue_all(tenant_a, wo, 100)
    r1 = receive(tenant_a, wo, 40)
    wo.refresh_from_db()
    assert r1.total_cost == D("400.00") and wo.status == WorkOrder.Status.IN_PROGRESS
    r2 = receive(tenant_a, wo, 60)
    wo.refresh_from_db()
    assert r2.total_cost == D("600.00") and r2.is_final
    assert wo.status == WorkOrder.Status.COMPLETED
    assert wo.cost_received == D("1000.00") and wo.wip_value == D("0.00")
    assert StockBalance.objects.get(company=company, product=fg).on_hand == D(100)
    assert account_net(company, "1450") == D("0.00")
    assert account_net(company, "1400") == D("0.00")                      # taken out, then received back in


def test_a_receipt_before_full_issue_is_not_underpriced(tenant_a, method):
    _c, _fg, _comp, _bom, wo = setup_order(tenant_a, method, qty=100, per_unit=1, cost=10)
    issue_all(tenant_a, wo, 40)                       # only 40 units' material so far
    r1 = receive(tenant_a, wo, 40)
    assert r1.total_cost == D("400.00")               # not 40 % of the pool (₹160)


def test_final_receipt_carries_a_price_rise_in_the_materials(tenant_a, method):
    company, fg, comp, _bom, wo = setup_order(tenant_a, method, qty=100, per_unit=1, cost=10)
    issue_all(tenant_a, wo, 100)
    receive(tenant_a, wo, 40)
    # The order used 10 more than planned, bought dearer.
    InventoryService.post_movement(
        company=company, product=comp, movement_type=MovementType.PURCHASE, quantity=D(50), unit_cost=D(20),
        user=tenant_a.owner,
    )
    wl = wo.component_lines.get()
    extra = issue_svc.create_issue(wo, tenant_a.owner, [{"wo_line": wl, "qty": 10, "extra_reason": "Re-mix"}])
    issue_svc.post_issue(extra, tenant_a.owner)
    wo.refresh_from_db()
    final = receive(tenant_a, wo, 60, final=True)
    wo.refresh_from_db()
    assert wo.wip_value == D("0.00")
    assert final.total_cost == wo.cost_issued - D("400.00")      # the last batch takes the true-up


def test_receipt_beyond_the_pool_is_refused_unless_a_manager_overrides(tenant_a, method):
    _c, _fg, _comp, _bom, wo = setup_order(tenant_a, method, qty=100, per_unit=1, cost=10)
    issue_all(tenant_a, wo, 30)
    rec = receipt_svc.create_receipt(wo, tenant_a.owner, {"lines": [{"kind": "MAIN", "qty_good": 50}]})
    with pytest.raises(BusinessRuleError) as exc:
        receipt_svc.post_receipt(rec, tenant_a.owner)
    assert exc.value.get_codes() == "MFG_RECEIPT_EXCEEDS_WIP"
    with pytest.raises(BusinessRuleError):
        receipt_svc.post_receipt(rec, tenant_a.owner, override_wip=True, is_manager=False)
    posted = receipt_svc.post_receipt(rec, tenant_a.owner, override_wip=True, is_manager=True)
    wo.refresh_from_db()
    assert posted.total_cost == D("500.00") and wo.wip_value == D("-200.00")


def test_receipt_cannot_run_far_past_the_plan(tenant_a, method):
    _c, _fg, _comp, _bom, wo = setup_order(tenant_a, method, qty=100)
    issue_all(tenant_a, wo, 100)
    rec = receipt_svc.create_receipt(wo, tenant_a.owner, {"lines": [{"kind": "MAIN", "qty_good": 125}]})
    with pytest.raises(BusinessRuleError) as exc:
        receipt_svc.post_receipt(rec, tenant_a.owner)
    assert exc.value.get_codes() == "MFG_OVER_RECEIPT"


def test_materials_without_cost_cannot_be_received(tenant_a, method):
    _c, _fg, _comp, _bom, wo = setup_order(tenant_a, method, qty=10, cost=0)
    issue_all(tenant_a, wo, 10)
    rec = receipt_svc.create_receipt(wo, tenant_a.owner, {"lines": [{"kind": "MAIN", "qty_good": 10}]})
    with pytest.raises(BusinessRuleError) as exc:
        receipt_svc.post_receipt(rec, tenant_a.owner)
    assert exc.value.get_codes() == "MFG_ZERO_COST_COMPLETE"


def test_by_product_takes_its_value_off_the_pool_first(tenant_a, method):
    company = prepare(tenant_a, method=method)
    bp = make_product(company, sku="BP-1", name="Husk")
    fg = make_product(company, sku="FG-BP")
    comp = stocked(tenant_a, "COMP-BP", 1000, 10)
    bom = make_bom(
        company, fg, [(comp, 1)], user=tenant_a.owner,
        outputs=[{"product": bp, "kind": "BY_PRODUCT", "qty": D("0.1"), "recovery_rate": D("5")}],
    )
    wo = release_work_order(make_wo(company, bom, 100, user=tenant_a.owner), tenant_a.owner)
    issue_all(tenant_a, wo, 100)
    assert wo.planned_outputs.get().qty == D("10.000")
    rec = receipt_svc.create_receipt(wo, tenant_a.owner, {"is_final": True})     # planned outputs filled in
    rec = receipt_svc.post_receipt(rec, tenant_a.owner)
    assert StockBalance.objects.get(company=company, product=bp).on_hand == D(10)
    by_line = rec.lines.get(kind="BY_PRODUCT")
    assert by_line.cost_amount == D("50.00")                                      # 10 kg at ₹5
    main_line = rec.lines.get(kind="MAIN")
    assert main_line.cost_amount == D("950.00")                                   # the rest of the ₹1,000
    wo.refresh_from_db()
    assert wo.wip_value == D("0.00")


def test_co_products_split_the_pool_by_share(tenant_a, method):
    company = prepare(tenant_a, method=method)
    co = make_product(company, sku="CO-1", name="Co")
    fg = make_product(company, sku="FG-CO")
    comp = stocked(tenant_a, "COMP-CO", 1000, 10)
    bom = make_bom(
        company, fg, [(comp, 1)], user=tenant_a.owner,
        outputs=[{"product": co, "kind": "CO_PRODUCT", "qty": D("0.5"), "cost_share_pct": D("20")}],
    )
    wo = release_work_order(make_wo(company, bom, 100, user=tenant_a.owner), tenant_a.owner)
    assert wo.estimated_unit_cost == D("8.0000")                                   # 80 % of ₹1,000 over 100 units
    assert wo.planned_outputs.get().estimated_unit_cost == D("4.0000")             # 20 % over 50 units
    issue_all(tenant_a, wo, 100)
    rec = receipt_svc.post_receipt(receipt_svc.create_receipt(wo, tenant_a.owner, {"is_final": True}), tenant_a.owner)
    assert rec.lines.get(kind="MAIN").cost_amount == D("800.00")
    assert rec.lines.get(kind="CO_PRODUCT").cost_amount == D("200.00")


def test_rework_and_rejected_units_go_to_their_own_godowns(tenant_a, method):
    company, fg, _comp, _bom, wo = setup_order(tenant_a, method, qty=100, per_unit=1, cost=10)
    issue_all(tenant_a, wo, 100)
    rec = receive(tenant_a, wo, 90, final=True, rejected=5, rework=5)
    wo.refresh_from_db()
    good_wh = InventoryService.default_warehouse(company)
    qrn = Warehouse.objects.get(company=company, kind="QUARANTINE")
    scrap = Warehouse.objects.get(company=company, kind="SCRAP")
    assert StockBalance.objects.get(company=company, product=fg, warehouse=good_wh).on_hand == D(90)
    assert StockBalance.objects.get(company=company, product=fg, warehouse=qrn).on_hand == D(5)
    assert StockBalance.objects.get(company=company, product=fg, warehouse=scrap).on_hand == D(5)
    # The 95 usable units carry all ₹1,000 (the rejected 5 take nothing); the rework units cost the same each.
    unit = D("1000") / D(95)
    assert abs(rec.lines.get().unit_cost - unit.quantize(D("0.0001"))) < D("0.0001")
    assert wo.qty_completed == 90 and wo.qty_rework == 5 and wo.qty_rejected == 5
    assert wo.wip_value.copy_abs() < D("0.10")
    # Neither godown is offered for a sale.
    assert qrn.pk not in Warehouse.objects.selectable("SALE", company).values_list("pk", flat=True)


def test_batch_tracked_output_gets_a_lot_with_dates(tenant_a, method):
    company = prepare(tenant_a, method=method)
    fg = make_product(company, sku="FG-BT", track_batch=True)
    comp = stocked(tenant_a, "COMP-BT", 100, 4)
    bom = make_bom(company, fg, [(comp, 1)], user=tenant_a.owner)
    wo = release_work_order(make_wo(company, bom, 10, user=tenant_a.owner), tenant_a.owner)
    issue_all(tenant_a, wo, 10)
    exp = timezone.localdate() + timedelta(days=180)
    receive(tenant_a, wo, 10, final=True, batch_no="B-001", exp_date=exp)
    lot = BatchLot.objects.get(company=company, product=fg, batch_no="B-001")
    assert lot.expiry_date == exp
    wo.refresh_from_db()
    assert wo.batch_id == lot.pk


def test_backflush_takes_the_material_when_output_is_received(tenant_a, method):
    company = prepare(tenant_a, method=method)
    fg = make_product(company, sku="FG-BF")
    comp = stocked(tenant_a, "COMP-BF", 500, 10)
    bom = make_bom(company, fg, [{"component": comp, "qty": D("2"), "issue_method": "BACKFLUSH"}], user=tenant_a.owner)
    wo = release_work_order(make_wo(company, bom, 50, user=tenant_a.owner), tenant_a.owner)
    with pytest.raises(BusinessRuleError):                        # the default issue skips backflush lines
        issue_svc.create_issue(wo, tenant_a.owner)
    rec = receive(tenant_a, wo, 20)                               # 20 units made -> 40 taken
    wo.refresh_from_db()
    assert rec.backflush_issue_id and wo.component_lines.get().qty_issued == D(40)
    assert wo.cost_issued == D("400.00") and rec.total_cost == D("400.00")
    final = receive(tenant_a, wo, 30, final=True)
    wo.refresh_from_db()
    assert wo.component_lines.get().qty_issued == D(100) and wo.wip_value == D("0.00")
    assert final.total_cost == D("600.00")


def test_additional_cost_is_absorbed_into_finished_goods_only_with_the_costing_flag(tenant_a, method):
    company = prepare(tenant_a, method=method, costing_gl=True)
    fg = make_product(company, sku="FG-AC")
    comp = stocked(tenant_a, "COMP-AC", 1000, 10)
    bom = make_bom(
        company, fg, [(comp, 100)], user=tenant_a.owner, output_qty="100",     # 100 per batch of 100
        additional=[{"label": "Grinding", "basis": "PER_BATCH", "amount": D("500")}],
    )
    wo = release_work_order(make_wo(company, bom, 100, user=tenant_a.owner), tenant_a.owner)
    assert wo.estimated_unit_cost == D("15.0000")                  # ₹1,000 materials + ₹500 per batch
    issue_all(tenant_a, wo, 100)
    rec = receive(tenant_a, wo, 100, final=True)
    wo.refresh_from_db()
    assert rec.absorbed_cost == D("500.00") and rec.total_cost == D("1500.00")
    assert wo.cost_absorbed == D("500.00") and wo.wip_value == D("0.00")
    assert account_net(company, "5410") == D("-500.00")
    assert account_net(company, "1450") == D("0.00")


def test_additional_cost_is_ignored_without_the_costing_flag(tenant_a, method):
    company = prepare(tenant_a, method=method, costing_gl=False)
    fg = make_product(company, sku="FG-AC2")
    comp = stocked(tenant_a, "COMP-AC2", 1000, 10)
    bom = make_bom(
        company, fg, [(comp, 1)], user=tenant_a.owner,
        additional=[{"label": "Grinding", "basis": "PER_UNIT", "amount": D("5")}],
    )
    wo = release_work_order(make_wo(company, bom, 10, user=tenant_a.owner), tenant_a.owner)
    assert wo.estimated_unit_cost == D("10.0000")
    issue_all(tenant_a, wo, 10)
    assert receive(tenant_a, wo, 10, final=True).absorbed_cost == 0


# --- close ------------------------------------------------------------------------------------

def test_close_reports_usage_variance_and_clears_wip(tenant_a, method):
    company, _fg, _comp, _bom, wo = setup_order(tenant_a, method, qty=100, per_unit=1, cost=10)
    wl = wo.component_lines.get()
    issue_svc.post_issue(issue_svc.create_issue(wo, tenant_a.owner, [{"wo_line": wl, "qty": 100}]), tenant_a.owner)
    extra = issue_svc.create_issue(wo, tenant_a.owner, [{"wo_line": wl, "qty": 5, "extra_reason": "Spill"}])
    issue_svc.post_issue(extra, tenant_a.owner)
    receive(tenant_a, wo, 100, final=True)
    wo.refresh_from_db()
    assert wo.status == WorkOrder.Status.COMPLETED
    closed = flow.close_work_order(wo, tenant_a.owner)
    assert closed.status == WorkOrder.Status.CLOSED and closed.closed_at
    usage = closed.variances.get(kind="USAGE")
    assert usage.standard_qty == D(100) and usage.actual_qty == D(105)
    assert usage.variance == D("50.00")                              # used 5 more than the plan allows
    assert closed.wip_value == D("0.00")
    assert account_net(company, "1450") == D("0.00")


def test_close_clears_a_short_closed_orders_leftover_to_variance_and_can_reopen(tenant_a, method):
    company, fg, _comp, _bom, wo = setup_order(tenant_a, method, qty=100, per_unit=1, cost=10)
    issue_all(tenant_a, wo, 100)
    receive(tenant_a, wo, 60)                                        # stops at 60 of 100
    wo.refresh_from_db()
    flow.complete_separate(wo, tenant_a.owner)
    wo.refresh_from_db()
    assert wo.wip_value == D("400.00")                               # the unmade 40 units' material
    flow.close_work_order(wo, tenant_a.owner)
    wo.refresh_from_db()
    assert wo.cost_variance == D("400.00") and wo.wip_value == D("0.00")
    assert account_net(company, "5420") == D("400.00") and account_net(company, "1450") == D("0.00")
    flow.reopen_work_order(wo, tenant_a.owner, "Closed too early")
    wo.refresh_from_db()
    assert wo.status == WorkOrder.Status.COMPLETED and wo.cost_variance == 0
    assert account_net(company, "5420") == D("0.00") and wo.variances.count() == 0


def test_only_a_completed_order_can_close(tenant_a, method):
    _c, _fg, _comp, _bom, wo = setup_order(tenant_a, method, qty=10)
    with pytest.raises(BusinessRuleError) as exc:
        flow.close_work_order(wo, tenant_a.owner)
    assert exc.value.get_codes() == "MFG_BAD_WO_STATUS"


def test_complete_needs_a_receipt_first(tenant_a, method):
    _c, _fg, _comp, _bom, wo = setup_order(tenant_a, method, qty=10)
    with pytest.raises(BusinessRuleError) as exc:
        flow.complete_separate(wo, tenant_a.owner)
    assert exc.value.get_codes() == "MFG_NOTHING_RECEIVED"


# --- reversal order (§4.12) --------------------------------------------------------------------

def test_reversal_order_rules(tenant_a, method):
    company, fg, comp, _bom, wo = setup_order(tenant_a, method, qty=100, per_unit=1, cost=10)
    issue = issue_all(tenant_a, wo, 100)
    r1 = receive(tenant_a, wo, 40)
    r2 = receive(tenant_a, wo, 60, final=True)

    # An earlier receipt cannot go while a later one stands.
    with pytest.raises(BusinessRuleError) as exc:
        receipt_svc.reverse_receipt(r1, tenant_a.owner, "Wrong count")
    assert exc.value.get_codes() == "MFG_REVERSAL_ORDER"
    # The issue cannot go while finished goods carry its cost.
    with pytest.raises(BusinessRuleError) as exc:
        issue_svc.reverse_issue(issue, tenant_a.owner, "Typo")
    assert exc.value.get_codes() == "MFG_REVERSAL_ORDER"

    # Newest first works all the way back.
    receipt_svc.reverse_receipt(r2, tenant_a.owner, "Recount")
    wo.refresh_from_db()
    assert wo.status == WorkOrder.Status.IN_PROGRESS and wo.qty_completed == 40
    receipt_svc.reverse_receipt(r1, tenant_a.owner, "Recount")
    issue_svc.reverse_issue(issue, tenant_a.owner, "Typo")
    wo.refresh_from_db()
    assert wo.status == WorkOrder.Status.RELEASED
    assert wo.cost_issued == 0 and wo.cost_received == 0 and wo.wip_value == 0
    assert StockBalance.objects.get(company=company, product=comp).on_hand == D(1000)
    assert StockBalance.objects.get(company=company, product=fg).on_hand == D(0)
    assert account_net(company, "1450") == D("0.00") and account_net(company, "1400") == D("0.00")
    # The hold is back, so the order can be started again.
    assert StockBalance.objects.get(company=company, product=comp).reserved == D(100)


def test_output_that_has_been_sold_cannot_be_reversed(tenant_a, method):
    company, fg, _comp, _bom, wo = setup_order(tenant_a, method, qty=10, per_unit=1, cost=10)
    issue_all(tenant_a, wo, 10)
    rec = receive(tenant_a, wo, 10, final=True)
    InventoryService.post_movement(
        company=company, product=fg, movement_type=MovementType.SALE, quantity=D(4), unit_cost=D(10), user=tenant_a.owner,
    )
    with pytest.raises(BusinessRuleError) as exc:
        receipt_svc.reverse_receipt(rec, tenant_a.owner, "Mistake")
    assert exc.value.get_codes() == "MFG_REVERSAL_ORDER"


def test_nothing_can_be_reversed_on_a_closed_order(tenant_a, method):
    _c, _fg, _comp, _bom, wo = setup_order(tenant_a, method, qty=10)
    issue = issue_all(tenant_a, wo, 10)
    receive(tenant_a, wo, 10, final=True)
    wo.refresh_from_db()
    flow.close_work_order(wo, tenant_a.owner)
    with pytest.raises(BusinessRuleError) as exc:
        issue_svc.reverse_issue(issue, tenant_a.owner, "Oops")
    assert exc.value.get_codes() == "MFG_REVERSAL_ORDER"


def test_a_reason_is_required_to_reverse(tenant_a, method):
    _c, _fg, _comp, _bom, wo = setup_order(tenant_a, method, qty=10)
    issue = issue_all(tenant_a, wo, 10)
    with pytest.raises(BusinessRuleError) as exc:
        issue_svc.reverse_issue(issue, tenant_a.owner, "  ")
    assert exc.value.get_codes() == "MFG_REASON_REQUIRED"


def test_cancel_after_documents_asks_for_them_to_be_reversed_first(tenant_a, method):
    _c, _fg, _comp, _bom, wo = setup_order(tenant_a, method, qty=10)
    issue = issue_all(tenant_a, wo, 5)
    wo.refresh_from_db()
    with pytest.raises(BusinessRuleError) as exc:
        flow.cancel_separate(wo, tenant_a.owner)
    assert exc.value.get_codes() == "MFG_CANCEL_REVERSE_FIRST"
    issue_svc.reverse_issue(issue, tenant_a.owner, "Cancelling")
    wo.refresh_from_db()
    flow.cancel_separate(wo, tenant_a.owner)
    assert not StockReservation.objects.filter(reference_type="work_order", released_at__isnull=True).exists()


# --- genealogy --------------------------------------------------------------------------------

def test_inputs_are_linked_to_the_output_lot(tenant_a, method):
    from inventory.models import TraceLink

    company = prepare(tenant_a, method=method)
    fg = make_product(company, sku="TR-FG", track_batch=True)
    comp = make_product(company, sku="TR-COMP", track_batch=True, purchase_price="4")
    in_lot = BatchLot.objects.create(company=company, product=comp, batch_no="SUP-77", expiry_date=timezone.localdate() + timedelta(days=90))
    InventoryService.post_movement(
        company=company, product=comp, batch=in_lot, movement_type=MovementType.PURCHASE, quantity=D(100),
        unit_cost=D(4), user=tenant_a.owner,
    )
    bom = make_bom(company, fg, [(comp, 1)], user=tenant_a.owner)
    wo = release_work_order(make_wo(company, bom, 10, user=tenant_a.owner), tenant_a.owner)
    issue_all(tenant_a, wo, 10)
    receive(tenant_a, wo, 10, final=True, batch_no="FG-9", exp_date=timezone.localdate() + timedelta(days=60))
    link = TraceLink.objects.get(company=company, work_order_id=wo.pk, reversed_at__isnull=True)
    assert link.input_batch.batch_no == "SUP-77" and link.output_batch.batch_no == "FG-9"


# --- API --------------------------------------------------------------------------------------

def test_the_whole_flow_through_the_api(tenant_a):
    company = prepare(tenant_a, method="WAVG")
    fg = make_product(company, sku="API-FG")
    comp = stocked(tenant_a, "API-COMP", 500, 10)
    bom = make_bom(company, fg, [(comp, 1)], user=tenant_a.owner)
    c = tenant_a.client
    wo = body(c.post("/api/v1/manufacturing/work-orders/", {"bom": bom.id, "qty": "20", "due_date": "2030-01-31"}, format="json"))
    assert wo["number"].startswith("WO-") and wo["issue_mode"] == "SEPARATE"
    assert c.post(f"/api/v1/manufacturing/work-orders/{wo['id']}/release/").status_code == 200

    issue = c.post("/api/v1/manufacturing/material-issues/", {"work_order": wo["id"]}, format="json", HTTP_IDEMPOTENCY_KEY="a1")
    assert issue.status_code == 201, issue.data
    issue_id = body(issue)["id"]
    posted = c.post(f"/api/v1/manufacturing/material-issues/{issue_id}/post/", format="json", HTTP_IDEMPOTENCY_KEY="a2")
    assert posted.status_code == 200 and body(posted)["status"] == "POSTED"
    replay = c.post(f"/api/v1/manufacturing/material-issues/{issue_id}/post/", format="json", HTTP_IDEMPOTENCY_KEY="a2")
    assert replay.status_code == 200
    assert StockMovement.objects.filter(reference_type="mfg_issue", reference_id=str(issue_id)).count() == 1

    receipt = c.post("/api/v1/manufacturing/production-receipts/", {"work_order": wo["id"], "is_final": True}, format="json")
    assert receipt.status_code == 201, receipt.data
    rid = body(receipt)["id"]
    done = c.post(f"/api/v1/manufacturing/production-receipts/{rid}/post/", format="json")
    assert done.status_code == 200, done.data
    assert Decimal(body(done)["total_cost"]) == D("200.00")

    closed = c.post(f"/api/v1/manufacturing/work-orders/{wo['id']}/close/")
    assert closed.status_code == 200 and body(closed)["status"] == "CLOSED"

    # A bad reversal says why, with a code.
    rev = c.post(f"/api/v1/manufacturing/material-issues/{issue_id}/reverse/", {"reason": "oops"}, format="json")
    assert rev.status_code == 400 and "MFG_REVERSAL_ORDER" in str(rev.data)


def test_inventory_staff_work_but_cannot_reverse_or_see_costs(tenant_a):
    company = prepare(tenant_a, method="WAVG")
    fg = make_product(company, sku="IS-FG")
    comp = stocked(tenant_a, "IS-COMP", 100, 10)
    bom = make_bom(company, fg, [(comp, 1)], user=tenant_a.owner)
    wo = release_work_order(make_wo(company, bom, 5, user=tenant_a.owner), tenant_a.owner)
    _u, inv = member(tenant_a, "INVENTORY_STAFF", can_manage_inventory=True)
    made = inv.post("/api/v1/manufacturing/material-issues/", {"work_order": wo.id}, format="json")
    assert made.status_code == 201
    assert "cost_amount" not in str(body(made)["lines"][0])
    issue_id = body(made)["id"]
    assert inv.post(f"/api/v1/manufacturing/material-issues/{issue_id}/post/").status_code == 200
    assert inv.post(f"/api/v1/manufacturing/material-issues/{issue_id}/reverse/", {"reason": "x"}, format="json").status_code == 403


def test_the_work_order_sheet_and_issue_slip_print_without_any_cost(tenant_a):
    from manufacturing.services import issue as isv

    company = prepare(tenant_a)
    raw = stocked(tenant_a, "PR-RAW", 100, 10)
    fg = make_product(company, sku="PR-FG", name="Print widget")
    bom = make_bom(company, fg, [(raw, 2)], user=tenant_a.owner)
    wo = make_wo(company, bom, 5, user=tenant_a.owner)
    release_work_order(wo, tenant_a.owner)
    doc = isv.post_issue(isv.create_issue(wo, tenant_a.owner, None), tenant_a.owner)
    sheet = tenant_a.client.get(f"/api/v1/manufacturing/work-orders/{wo.pk}/print/")
    assert sheet.status_code == 200 and sheet["Content-Type"].startswith("text/html")
    html = sheet.content.decode()
    assert wo.number in html and "Print widget" in html and "PR-RAW" in html and "Checked by" in html
    assert "100.00" not in html and "₹" not in html            # no money on the floor copy
    slip = tenant_a.client.get(f"/api/v1/manufacturing/material-issues/{doc.pk}/print/")
    assert slip.status_code == 200 and doc.number in slip.content.decode()
    _, sales = member(tenant_a, "SALES_STAFF")
    assert sales.get(f"/api/v1/manufacturing/work-orders/{wo.pk}/print/").status_code in (403, 404)


# --- asking a manager to approve extra material (instead of a manager-only post) ---------------------

def test_extra_material_can_be_asked_for_and_approved_by_a_manager(tenant_a, method):
    _c, _fg, comp, _bom, wo = setup_order(tenant_a, method, qty=100, per_unit=1)
    _u, floor = member(tenant_a, "INVENTORY_STAFF", can_manage_inventory=True)
    wl = wo.component_lines.get()
    base = "/api/v1/manufacturing"
    made = floor.post(f"{base}/material-issues/", {
        "workOrder": wo.pk, "lines": [{"woLine": wl.pk, "qty": "130", "extraReason": "Spillage in the mixer"}],
    }, format="json", HTTP_IDEMPOTENCY_KEY="ap-1")
    assert made.status_code == 201, made.data
    issue_id = body(made)["id"]
    # the floor cannot post it, but can ask
    refused = floor.post(f"{base}/material-issues/{issue_id}/post/", {}, format="json", HTTP_IDEMPOTENCY_KEY="ap-2")
    assert refused.status_code == 400 and "MFG_EXTRA_NEEDS_MANAGER" in str(refused.data)
    asked = floor.post(f"{base}/material-issues/{issue_id}/request-approval/", {"note": "need it today"}, format="json")
    assert asked.status_code == 200, asked.data
    assert body(asked)["approval"] == "REQUESTED" and body(asked)["status"] == "DRAFT"
    again = floor.post(f"{base}/material-issues/{issue_id}/request-approval/", {}, format="json")
    assert again.status_code == 400 and "MFG_APPROVAL_PENDING" in str(again.data)
    assert floor.post(f"{base}/material-issues/{issue_id}/approve/", {}, format="json").status_code == 403
    waiting = tenant_a.client.get(f"{base}/material-issues/?approval=REQUESTED")
    assert [r["id"] for r in (body(waiting)["results"] if "results" in body(waiting) else body(waiting))] == [issue_id]
    done = tenant_a.client.post(f"{base}/material-issues/{issue_id}/approve/", {"note": "ok"}, format="json", HTTP_IDEMPOTENCY_KEY="ap-3")
    assert done.status_code == 200, done.data
    assert body(done)["status"] == "POSTED" and body(done)["approval"] == "APPROVED"
    wo.refresh_from_db()
    assert wo.cost_issued == D("1300.00")


def test_a_turned_down_request_stays_a_draft_and_can_be_asked_again(tenant_a, method):
    _c, _fg, _comp, _bom, wo = setup_order(tenant_a, method, qty=100, per_unit=1)
    wl = wo.component_lines.get()
    doc = issue_svc.create_issue(wo, tenant_a.owner, [{"wo_line": wl, "qty": 130, "extra_reason": "Spill"}])
    issue_svc.request_approval(doc, tenant_a.owner, "please")
    with pytest.raises(BusinessRuleError) as exc:
        issue_svc.decide_approval(doc, tenant_a.owner, approve=False)
    assert exc.value.get_codes() == "MFG_REASON_REQUIRED"
    rejected = issue_svc.decide_approval(doc, tenant_a.owner, approve=False, note="Use the leftover first")
    assert rejected.approval == "REJECTED" and rejected.status == DocumentStatus.DRAFT
    assert issue_svc.request_approval(rejected, tenant_a.owner).approval == "REQUESTED"


def test_nothing_to_approve_when_the_issue_is_within_the_plan(tenant_a, method):
    _c, _fg, _comp, _bom, wo = setup_order(tenant_a, method, qty=100, per_unit=1)
    doc = issue_svc.create_issue(wo, tenant_a.owner)
    with pytest.raises(BusinessRuleError) as exc:
        issue_svc.request_approval(doc, tenant_a.owner)
    assert exc.value.get_codes() == "MFG_APPROVAL_NOT_NEEDED"
