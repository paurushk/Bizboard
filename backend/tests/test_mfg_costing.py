"""Manufacturing phase 5: conversion cost, standard costing, reports, reconciliation, period close."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.invariants import assert_all_invariants
from inventory.models import StockBalance, StockMovement
from manufacturing.models import StandardCost, WorkOrder
from manufacturing.services import flow, issue as issue_svc, receipt as receipt_svc, release_work_order, reports
from tests.conftest import create_draft_invoice, make_customer, make_product
from tests.mfg_helpers import account_net, body, make_bom, make_wo, member, prepare, stocked

pytestmark = pytest.mark.django_db


def D(v):
    return Decimal(str(v))


@pytest.fixture(params=["WAVG", "FIFO"])
def method(request):
    return request.param


def run_order(tenant, wo, *, issue_qty=None, good=None, final=True, **doc):
    wl = wo.component_lines.get()
    issue_svc.post_issue(issue_svc.create_issue(wo, tenant.owner, [{"wo_line": wl, "qty": issue_qty or wl.qty}]), tenant.owner)
    lines = [{"kind": "MAIN", "qty_good": good if good is not None else wo.qty}]
    return receipt_svc.post_receipt(
        receipt_svc.create_receipt(wo, tenant.owner, {"is_final": final, "lines": lines, **doc}), tenant.owner,
    )


# --- conversion cost by element ----------------------------------------------------------------------

def test_labour_and_overhead_are_credited_to_their_own_accounts(tenant_a, method):
    company = prepare(tenant_a, method=method, costing_gl=True)
    fg = make_product(company, sku="CC-FG")
    comp = stocked(tenant_a, "CC-C", 1000, 10)
    bom = make_bom(
        company, fg, [(comp, 100)], user=tenant_a.owner, output_qty="100",
        additional=[
            {"label": "Grinding labour", "element": "LABOUR", "basis": "PER_BATCH", "amount": D("300")},
            {"label": "Power", "element": "OVERHEAD", "basis": "PER_UNIT", "amount": D("1")},
            {"label": "Packing", "basis": "PER_BATCH", "amount": D("50")},
        ],
    )
    wo = release_work_order(make_wo(company, bom, 100, user=tenant_a.owner), tenant_a.owner)
    assert wo.estimated_unit_cost == D("14.5000")            # 1000 of material + 450 of conversion, over 100
    rec = run_order(tenant_a, wo)
    wo.refresh_from_db()
    assert rec.absorbed_cost == D("450.00") and rec.total_cost == D("1450.00")
    assert account_net(company, "5430") == D("-300.00")
    assert account_net(company, "5440") == D("-100.00")
    assert account_net(company, "5410") == D("-50.00")
    assert wo.wip_value == 0 and account_net(company, "1450") == 0
    assert StockMovement.objects.get(movement_type="MANUFACTURE_RECEIPT").unit_cost == D("14.5000")
    assert_all_invariants(company)


def test_conversion_cost_is_left_out_when_the_costing_flag_is_off(tenant_a, method):
    company = prepare(tenant_a, method=method, costing_gl=False)
    fg = make_product(company, sku="CC2-FG")
    comp = stocked(tenant_a, "CC2-C", 1000, 10)
    bom = make_bom(company, fg, [(comp, 1)], user=tenant_a.owner, additional=[{"label": "Labour", "element": "LABOUR", "basis": "PER_UNIT", "amount": D("5")}])
    wo = release_work_order(make_wo(company, bom, 10, user=tenant_a.owner), tenant_a.owner)
    assert run_order(tenant_a, wo).absorbed_cost == 0 and account_net(company, "5430") == 0


# --- standard costing ----------------------------------------------------------------------------------

def standard_world(tenant, method, std):
    company = prepare(tenant, method=method, costing_gl=True)
    fg = make_product(company, sku="STD-FG")
    comp = stocked(tenant, "STD-C", 1000, 10)
    StandardCost.objects.create(
        company=company, product=fg, effective_from=timezone.localdate() - timedelta(days=1),
        material=D(std) - D(4), labour=D(2), overhead=D(2), created_by=tenant.owner, updated_by=tenant.owner,
    )
    bom = make_bom(company, fg, [(comp, 1)], user=tenant.owner)
    wo = release_work_order(make_wo(company, bom, 100, user=tenant.owner), tenant.owner)
    return company, fg, comp, wo


def test_output_is_valued_at_standard_and_the_difference_clears_at_close(tenant_a, method):
    company, fg, comp, wo = standard_world(tenant_a, method, 12)          # actual cost is 10 a unit; standard is 12
    rec = run_order(tenant_a, wo)
    wo.refresh_from_db()
    assert rec.total_cost == D("1200.00")                                  # even the last receipt takes standard
    assert StockMovement.objects.get(movement_type="MANUFACTURE_RECEIPT").unit_cost == D("12.0000")
    assert wo.wip_value == D("-200.00")                                    # over-absorbed against what was issued
    flow.close_work_order(wo, tenant_a.owner)
    wo.refresh_from_db()
    assert wo.cost_variance == D("-200.00") and wo.wip_value == 0
    assert account_net(company, "5420") == D("-200.00") and account_net(company, "1450") == 0
    assert_all_invariants(company)


def test_actual_cost_above_standard_is_an_unfavourable_variance(tenant_a, method):
    company, fg, comp, wo = standard_world(tenant_a, method, 8)
    run_order(tenant_a, wo)
    wo.refresh_from_db()
    flow.close_work_order(wo, tenant_a.owner)
    assert account_net(company, "5420") == D("200.00")                    # cost 1000 against 800 of output
    assert StockBalance.objects.get(company=company, product=fg).on_hand == D(100)


def test_a_standard_in_force_on_the_date_is_used_and_a_later_one_is_not(tenant_a, method):
    company = prepare(tenant_a, method=method, costing_gl=True)
    fg = make_product(company, sku="STD2-FG")
    comp = stocked(tenant_a, "STD2-C", 1000, 10)
    today = timezone.localdate()
    for start, material in ((today - timedelta(days=30), 9), (today + timedelta(days=30), 99)):
        StandardCost.objects.create(company=company, product=fg, effective_from=start, material=D(material))
    wo = release_work_order(make_wo(company, make_bom(company, fg, [(comp, 1)], user=tenant_a.owner), 10, user=tenant_a.owner), tenant_a.owner)
    assert run_order(tenant_a, wo).total_cost == D("90.00")


def test_without_the_costing_flag_a_standard_is_ignored(tenant_a, method):
    company = prepare(tenant_a, method=method, costing_gl=False)
    fg = make_product(company, sku="STD3-FG")
    comp = stocked(tenant_a, "STD3-C", 1000, 10)
    StandardCost.objects.create(company=company, product=fg, effective_from=timezone.localdate() - timedelta(days=1), material=D(50))
    wo = release_work_order(make_wo(company, make_bom(company, fg, [(comp, 1)], user=tenant_a.owner), 10, user=tenant_a.owner), tenant_a.owner)
    assert run_order(tenant_a, wo).total_cost == D("100.00")


def test_standard_costs_api_follows_roles_and_the_flag(tenant_a):
    company = prepare(tenant_a, costing_gl=False)
    fg = make_product(company, sku="STD4-FG")
    assert tenant_a.client.get("/api/v1/manufacturing/standard-costs/").status_code == 404
    prepare(tenant_a, costing_gl=True)
    _a, acc = member(tenant_a, "ACCOUNTANT")
    _i, inv = member(tenant_a, "INVENTORY_STAFF", can_manage_inventory=True)
    made = acc.post("/api/v1/manufacturing/standard-costs/", {
        "product": fg.pk, "effective_from": str(timezone.localdate()), "material": "8", "labour": "2", "overhead": "1",
    }, format="json")
    assert made.status_code == 201, made.data
    assert D(body(made)["unit_cost"]) == D("11")
    assert inv.get("/api/v1/manufacturing/standard-costs/").status_code == 403           # costs are not for the floor
    assert inv.post("/api/v1/manufacturing/standard-costs/", {"product": fg.pk, "effective_from": "2030-01-01"}, format="json").status_code == 403
    assert acc.post("/api/v1/manufacturing/standard-costs/", {
        "product": fg.pk, "effective_from": str(timezone.localdate()), "material": "9",
    }, format="json").status_code == 400                                                   # one standard per start date


# --- reports -------------------------------------------------------------------------------------------

def reports_world(tenant, method):
    company = prepare(tenant, method=method)
    fg = make_product(company, sku="RP-FG", name="Report FG")
    scrap = make_product(company, sku="RP-SC", name="Husk")
    comp = stocked(tenant, "RP-C", 1000, 10)
    bom = make_bom(
        company, fg, [(comp, 1)], user=tenant.owner,
        outputs=[{"product": scrap, "kind": "BY_PRODUCT", "qty": D("0.05"), "recovery_rate": D("2")}],
    )
    today = timezone.localdate()
    done = release_work_order(make_wo(company, bom, 100, user=tenant.owner, due_date=today), tenant.owner)
    wl = done.component_lines.get()
    issue_svc.post_issue(issue_svc.create_issue(done, tenant.owner, [{"wo_line": wl, "qty": 105, "extra_reason": "Spill"}]), tenant.owner)
    receipt_svc.post_receipt(receipt_svc.create_receipt(done, tenant.owner, {
        "is_final": True, "lines": [{"kind": "MAIN", "qty_good": 90, "qty_rejected": 6, "qty_rework": 4}, {"kind": "BY_PRODUCT", "product": scrap, "qty_good": 5}],
    }), tenant.owner)
    done.refresh_from_db()
    flow.close_work_order(done, tenant.owner)
    open_wo = release_work_order(make_wo(company, bom, 20, user=tenant.owner, due_date=today - timedelta(days=3)), tenant.owner)
    issue_svc.post_issue(issue_svc.create_issue(open_wo, tenant.owner), tenant.owner)
    return company, fg, scrap, comp, done, open_wo


def test_wip_report_ages_open_cost(tenant_a, method):
    company, fg, scrap, comp, done, open_wo = reports_world(tenant_a, method)
    rep = reports.wip_report(company)
    assert rep["total_wip"] == D("200.00") and len(rep["orders"]) == 1
    assert rep["orders"][0]["id"] == open_wo.pk and rep["buckets"]["0-7"] == D("200.00")
    old = reports.wip_report(company, as_of=timezone.localdate() + timedelta(days=45))
    assert old["orders"][0]["bucket"] == "31-90"


def test_cost_variance_and_yield_reports(tenant_a, method):
    company, fg, scrap, comp, done, open_wo = reports_world(tenant_a, method)
    today = timezone.localdate()
    cost = reports.work_order_cost_report(company, today, today)["orders"][0]
    assert cost["qty_made"] == D(94) and cost["yield_pct"] == D("94.0")                # 90 good + 4 rework of 100 planned
    var = reports.variance_report(company)
    item = var["items"][0]
    assert item["actual_qty"] == D(105) and item["standard_qty"] == D("100.000") and item["variance"] == D("50.00")
    yw = reports.yield_wastage_report(company)
    assert yw["orders"][0]["rejection_pct"] == D("6.0") and yw["orders"][0]["yield_pct"] == D("90.0")
    assert yw["scrap_and_byproducts"][0]["qty"] == D(5) and yw["scrap_and_byproducts"][0]["value"] == D("10.00")


def test_consumption_output_and_scrap_reports(tenant_a, method):
    company, fg, scrap, comp, done, open_wo = reports_world(tenant_a, method)
    cons = {r["name"]: r for r in reports.consumption_report(company)["items"]}
    assert cons["RP-C"]["qty"] == D(125) and cons["RP-C"]["cost"] == D("1250.00")        # 105 + 20 issued
    out = {(r["name"], r["kind"]): r for r in reports.output_report(company)["items"]}
    assert out[("Report FG", "MAIN")]["good"] == D(90) and out[("Report FG", "MAIN")]["rejected"] == D(6)
    reg = reports.scrap_register(company)["items"][0]
    assert reg["name"] == "Husk" and reg["made"] == D(5) and reg["on_hand"] == D(5) and reg["sold"] == 0


def test_on_time_report_counts_finished_and_late_orders(tenant_a, method):
    company, fg, scrap, comp, done, open_wo = reports_world(tenant_a, method)
    rep = reports.on_time_report(company)
    assert rep["finished_with_due_date"] == 1 and rep["on_time"] == 1 and rep["on_time_pct"] == D("100.0")
    assert rep["open_and_late"] == 1


def test_profitability_by_product_batch_and_customer(tenant_a, method):
    company = prepare(tenant_a, method=method)
    fg = make_product(company, sku="PR-FG", name="Profit FG", gst_rate="0")
    comp = stocked(tenant_a, "PR-C", 1000, 10)
    bom = make_bom(company, fg, [(comp, 2)], user=tenant_a.owner)
    wo = release_work_order(make_wo(company, bom, 50, user=tenant_a.owner), tenant_a.owner)
    run_order(tenant_a, wo)
    customer = make_customer(company, name="Big Buyer")
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": fg.id, "quantity": "10", "unit_price": "100", "gst_rate": "0"}], invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    by_product = reports.profitability(company)["rows"][0]
    assert by_product["name"] == "Profit FG" and by_product["qty"] == D(10)
    assert by_product["revenue"] == D("1000.00") and by_product["cost"] == D("200.00") and by_product["profit"] == D("800.00")
    assert by_product["margin_pct"] == D("80.0")
    assert reports.profitability(company, by="customer")["rows"][0]["name"] == "Big Buyer"
    assert reports.profitability(company, by="batch")["rows"][0]["name"] == "(no batch)"


def test_reconciliation_shows_wip_stage_split_and_job_worker_stock(tenant_a, method):
    company, fg, scrap, comp, done, open_wo = reports_world(tenant_a, method)
    rec = reports.reconciliation(company)
    assert rec["wip"]["gl_1450"] == D("200.00") and rec["wip"]["work_orders"] == D("200.00") and rec["wip"]["difference"] == 0
    assert "(unclassified)" in rec["inventory"]["by_stage"]
    assert set(rec["inventory"]["by_godown_kind"]) >= {"NORMAL", "QUARANTINE"}
    assert rec["job_work"]["difference"] == 0


def test_reports_api_roles_and_csv(tenant_a, method):
    company, fg, scrap, comp, done, open_wo = reports_world(tenant_a, method)
    api = tenant_a.client
    _i, inv = member(tenant_a, "INVENTORY_STAFF", can_manage_inventory=True)
    _a, acc = member(tenant_a, "ACCOUNTANT")
    for slug in ("wip", "work-order-cost", "variance", "scrap-register", "profitability", "reconciliation"):
        assert acc.get(f"/api/v1/manufacturing/reports/{slug}/").status_code == 200, slug
        assert inv.get(f"/api/v1/manufacturing/reports/{slug}/").status_code == 403, slug      # costs: not for the floor
    for slug in ("yield-wastage", "consumption", "output", "on-time"):
        assert inv.get(f"/api/v1/manufacturing/reports/{slug}/").status_code == 200, slug
    csv = api.get("/api/v1/manufacturing/reports/consumption/?export=csv")
    assert csv.status_code == 200 and csv["Content-Type"].startswith("text/csv") and b"RP-C" in csv.content
    assert api.get("/api/v1/manufacturing/reports/nonsense/").status_code == 400
    assert tenant_a.staff_client.get("/api/v1/manufacturing/reports/output/").status_code == 403


# --- closing the books -----------------------------------------------------------------------------------

def test_a_finished_but_unclosed_order_blocks_the_period_close(tenant_a, method):
    from accounting.services import BooksHealthService

    company = prepare(tenant_a, method=method)
    fg = make_product(company, sku="OW-FG")
    comp = stocked(tenant_a, "OW-C", 100, 10)
    bom = make_bom(company, fg, [(comp, 1)], user=tenant_a.owner)
    wo = release_work_order(make_wo(company, bom, 10, user=tenant_a.owner), tenant_a.owner)
    WorkOrder.objects.filter(pk=wo.pk).update(released_at=date(2026, 4, 10))
    run_order(tenant_a, wo)
    wo.refresh_from_db()
    assert wo.status == "COMPLETED"
    assert any(b["code"] == "OPEN_WIP" for b in BooksHealthService.period_close_blockers(company, period="2026-04"))
    flow.close_work_order(wo, tenant_a.owner)
    assert not any(b["code"] == "OPEN_WIP" for b in BooksHealthService.period_close_blockers(company, period="2026-04"))
