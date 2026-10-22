"""Manufacturing phase 4: job work out and in, challans, settlements, ageing, ITC-04."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.invariants import assert_all_invariants
from inventory.models import StockBalance, Warehouse
from inventory.services import InventoryService, InventoryValuationService
from jobwork.models import (
    Itc04Filing, JobWorkChallan, JobWorkChallanLine, JobWorkOrder, JobWorkSettlement, PrincipalMaterialMovement,
)
from jobwork.services import itc04, out, principal
from purchases.grn_service import GoodsReceiptService
from tests.conftest import make_customer, make_product, make_supplier
from tests.mfg_helpers import account_net, body, make_bom, make_wo, member, prepare, stocked
from tests.test_mfg_quality import grn

pytestmark = pytest.mark.django_db


def D(v):
    return Decimal(str(v))


@pytest.fixture(params=["WAVG", "FIFO"])
def method(request):
    return request.param


def jobwork_on(tenant, **extra):
    flags = dict(tenant.company.feature_flags or {})
    flags["MFG_JOB_WORK"] = True
    tenant.company.feature_flags = flags
    tenant.company.save(update_fields=["feature_flags"])


def world(tenant, method, raw_qty=100, cost=10):
    prepare(tenant, method=method)
    jobwork_on(tenant)
    c = tenant.company
    raw = stocked(tenant, "JW-RAW", raw_qty, cost)
    fin = make_product(c, sku="JW-FIN", name="Dyed cloth")
    sup = make_supplier(c, name="Ravi Dyers", gstin="29BBBBB1111B1Z5")
    order = out.create_order(c, tenant.owner, supplier=sup, process="Dyeing")
    return c, raw, fin, sup, order


def send(tenant, order, product, qty, **kw):
    ch = out.create_challan(order, tenant.owner, [{"product": product, "qty": qty, **kw}])
    return out.issue_challan(ch, tenant.owner)


def receive(tenant, order, lines, **kw):
    rc = out.create_receipt(order, tenant.owner, lines, **kw)
    return out.post_receipt(rc, tenant.owner)


def on_hand(c, product, warehouse=None):
    qs = StockBalance.objects.filter(company=c, product=product)
    if warehouse is not None:
        qs = qs.filter(warehouse=warehouse)
    return sum((b.on_hand for b in qs), D(0))


# --- sending ---------------------------------------------------------------------------------------

def test_a_challan_moves_stock_to_the_job_workers_godown_with_its_cost(tenant_a, method):
    c, raw, fin, sup, order = world(tenant_a, method)
    jw = order.job_worker_warehouse
    assert jw.kind == "JOB_WORKER" and jw.job_worker_id == sup.pk
    ch = send(tenant_a, order, raw, 60)
    assert ch.status == "ISSUED" and ch.number.startswith("JWC-")
    own = InventoryService.default_warehouse(c)
    assert on_hand(c, raw, own) == D(40) and on_hand(c, raw, jw) == D(60)
    line = ch.lines.get()
    assert line.unit_cost == D("10.0000") and line.qty_open == D(60)
    # Still our stock, still valued; the job worker's godown never appears in a sale picker.
    assert InventoryValuationService.unit_cost(c, raw, jw) == D("10")
    assert jw.pk not in Warehouse.objects.selectable("SALE", c).values_list("pk", flat=True)
    bal = out.balance_by_job_worker(c)
    assert bal == [{"supplier": sup.pk, "supplier_name": "Ravi Dyers", "product": raw.pk, "product_name": "JW-RAW", "qty": D(60), "value": D("600.00")}]
    assert_all_invariants(c)


def test_the_cost_that_goes_with_the_stock_is_the_cost_it_left_at(tenant_a, method):
    c, raw, fin, sup, order = world(tenant_a, method)
    InventoryService.post_movement(
        company=c, product=raw, movement_type="PURCHASE", quantity=D(100), unit_cost=D(30), user=tenant_a.owner,
    )
    own = InventoryService.default_warehouse(c)
    ch = send(tenant_a, order, raw, 150)
    # 100 at 10 and 50 at 30 under FIFO (avg 16.67... of 3000+1000 / 200 = 20 under WAVG).
    expected = D("16.6667") if method == "FIFO" else D("20.0000")
    assert ch.lines.get().unit_cost == expected
    jw = order.job_worker_warehouse
    assert InventoryValuationService.unit_cost(c, raw, jw).quantize(D("0.0001")) == expected


def test_a_challan_cannot_send_more_than_we_have(tenant_a, method):
    c, raw, fin, sup, order = world(tenant_a, method)
    ch = out.create_challan(order, tenant_a.owner, [{"product": raw, "qty": 500}])
    with pytest.raises(BusinessRuleError):
        out.issue_challan(ch, tenant_a.owner)
    assert on_hand(c, raw) == D(100)


def test_sending_twice_is_refused(tenant_a, method):
    c, raw, fin, sup, order = world(tenant_a, method)
    ch = out.create_challan(order, tenant_a.owner, [{"product": raw, "qty": 10}])
    out.issue_challan(ch, tenant_a.owner)
    with pytest.raises(BusinessRuleError) as exc:
        out.issue_challan(ch, tenant_a.owner)
    assert exc.value.get_codes() == "JW_DOC_NOT_DRAFT"


def test_an_unissued_challan_sends_nothing(tenant_a, method):
    c, raw, fin, sup, order = world(tenant_a, method)
    out.create_challan(order, tenant_a.owner, [{"product": raw, "qty": 10}])
    assert on_hand(c, raw, order.job_worker_warehouse) == 0


# --- receiving -------------------------------------------------------------------------------------

def test_processed_goods_cost_the_material_used_plus_the_job_charge(tenant_a, method):
    c, raw, fin, sup, order = world(tenant_a, method)
    send(tenant_a, order, raw, 60)
    rc = receive(tenant_a, order, [
        {"kind": "PROCESSED", "product": fin, "qty": 48, "input_product": raw, "input_qty": 50, "charge_amount": 100},
    ])
    own = InventoryService.default_warehouse(c)
    jw = order.job_worker_warehouse
    assert rc.number.startswith("JWR-")
    assert on_hand(c, raw, jw) == D(10) and on_hand(c, fin, own) == D(48)           # 50 used up, 10 still there
    line = rc.lines.get()
    assert line.unit_cost == D("12.5000") and line.cost_amount == D("600.00")        # (50 x 10 + 100) / 48
    cl = JobWorkChallanLine.objects.get()
    assert cl.qty_settled == D(50) and cl.qty_open == D(10)
    # The books: stock value up by exactly the job charge; the charge is absorbed, not double counted.
    assert account_net(c, "1400") == D("100.00") and account_net(c, "5410") == D("-100.00")
    assert_all_invariants(c)


def test_unprocessed_material_coming_back_returns_at_its_own_cost(tenant_a, method):
    c, raw, fin, sup, order = world(tenant_a, method)
    send(tenant_a, order, raw, 60)
    receive(tenant_a, order, [{"kind": "UNPROCESSED_RETURN", "product": raw, "qty": 25}])
    own = InventoryService.default_warehouse(c)
    assert on_hand(c, raw, own) == D(65) and on_hand(c, raw, order.job_worker_warehouse) == D(35)
    assert InventoryValuationService.unit_cost(c, raw, own).quantize(D("0.01")) == D("10.00")
    assert account_net(c, "1400") == 0
    assert_all_invariants(c)


def test_scrap_the_job_worker_keeps_is_written_off_as_a_loss(tenant_a, method):
    c, raw, fin, sup, order = world(tenant_a, method)
    send(tenant_a, order, raw, 10)
    receive(tenant_a, order, [
        {"kind": "SCRAP_RETAINED", "product": raw, "qty": 2},
        {"kind": "UNPROCESSED_RETURN", "product": raw, "qty": 8},
    ])
    assert on_hand(c, raw, order.job_worker_warehouse) == 0
    assert account_net(c, "5450") == D("20.00") and account_net(c, "1400") == D("-20.00")
    assert_all_invariants(c)


def test_scrap_sent_back_comes_off_the_cost_of_the_goods(tenant_a, method):
    c, raw, fin, sup, order = world(tenant_a, method)
    scrap = make_product(c, sku="JW-SCRAP", name="Cuttings")
    send(tenant_a, order, raw, 50)
    rc = receive(tenant_a, order, [
        {"kind": "PROCESSED", "product": fin, "qty": 48, "input_product": raw, "input_qty": 50},
        {"kind": "SCRAP_RETURNED", "product": scrap, "qty": 2, "unit_cost": 3},
    ])
    good = rc.lines.get(kind="PROCESSED")
    assert good.cost_amount == D("494.00")                 # 500 used less 6 of scrap worth keeping
    scrap_wh = Warehouse.objects.get(company=c, kind="SCRAP")
    assert on_hand(c, scrap, scrap_wh) == D(2)
    assert_all_invariants(c)


def test_more_than_was_sent_cannot_come_back(tenant_a, method):
    c, raw, fin, sup, order = world(tenant_a, method)
    send(tenant_a, order, raw, 60)
    with pytest.raises(BusinessRuleError) as exc:
        receive(tenant_a, order, [{"kind": "UNPROCESSED_RETURN", "product": raw, "qty": 61}])
    assert exc.value.get_codes() == "JW_OVER_RETURN"
    assert on_hand(c, raw, order.job_worker_warehouse) == D(60)         # nothing half-posted
    assert not JobWorkSettlement.objects.exists()


def test_the_oldest_challan_is_settled_first(tenant_a, method):
    c, raw, fin, sup, order = world(tenant_a, method)
    first = send(tenant_a, order, raw, 30)
    second = send(tenant_a, order, raw, 30)
    JobWorkChallan.objects.filter(pk=first.pk).update(challan_date=timezone.localdate() - timedelta(days=20))
    receive(tenant_a, order, [{"kind": "UNPROCESSED_RETURN", "product": raw, "qty": 40}])
    l1, l2 = first.lines.get(), second.lines.get()
    l1.refresh_from_db()
    l2.refresh_from_db()
    assert (l1.qty_settled, l2.qty_settled) == (D(30), D(10))
    assert_all_invariants(c)


def test_a_posted_receipt_cannot_be_posted_again(tenant_a, method):
    c, raw, fin, sup, order = world(tenant_a, method)
    send(tenant_a, order, raw, 10)
    rc = receive(tenant_a, order, [{"kind": "UNPROCESSED_RETURN", "product": raw, "qty": 5}])
    with pytest.raises(BusinessRuleError) as exc:
        out.post_receipt(rc, tenant_a.owner)
    assert exc.value.get_codes() == "JW_DOC_NOT_DRAFT"


# --- passing on and supplying from the job worker --------------------------------------------------------

def test_goods_passed_to_another_job_worker_get_a_challan_of_their_own(tenant_a, method):
    c, raw, fin, sup, order = world(tenant_a, method)
    sup2 = make_supplier(c, name="Shine Finishers", gstin="29CCCCC2222C1Z5")
    other = out.create_order(c, tenant_a.owner, supplier=sup2, process="Finishing")
    first = send(tenant_a, order, raw, 40)
    receive(tenant_a, order, [{"kind": "SENT_TO_OTHER", "product": raw, "qty": 25, "other_order": other.pk}])
    assert on_hand(c, raw, order.job_worker_warehouse) == D(15) and on_hand(c, raw, other.job_worker_warehouse) == D(25)
    onward = JobWorkChallan.objects.get(order=other)
    assert onward.origin == "FROM_OTHER_JOB_WORKER" and onward.source_challan_id == first.pk
    assert onward.lines.get().qty == D(25) and onward.lines.get().unit_cost == D("10.0000")
    assert_all_invariants(c)


def test_supplying_from_the_job_workers_premises_needs_the_declaration_and_an_invoice(tenant_a, method):
    c, raw, fin, sup, order = world(tenant_a, method)
    send(tenant_a, order, raw, 10)
    with pytest.raises(BusinessRuleError) as exc:
        receive(tenant_a, order, [{"kind": "SUPPLIED_FROM_JW", "product": raw, "qty": 4, "invoice_ref": "INV-9"}])
    assert exc.value.get_codes() == "JW_DIRECT_SUPPLY_NOT_DECLARED"
    JobWorkOrder.objects.filter(pk=order.pk).update(direct_supply_declared=True)
    order.refresh_from_db()
    with pytest.raises(BusinessRuleError) as exc:
        receive(tenant_a, order, [{"kind": "SUPPLIED_FROM_JW", "product": raw, "qty": 4}])
    assert exc.value.get_codes() == "JW_INVOICE_REQUIRED"


def test_supplier_shipping_straight_to_the_job_worker_writes_its_own_challan(tenant_a, method):
    c, raw, fin, sup, order = world(tenant_a, method)
    jw = order.job_worker_warehouse
    supplier = make_supplier(c, name="Yarn Mills")
    g, item = grn(tenant_a, supplier, raw, 200, price="8", warehouse=jw)
    GoodsReceiptService.complete(g, tenant_a.owner)
    g.refresh_from_db()
    assert on_hand(c, raw, jw) == D(200)
    ch = JobWorkChallan.objects.get(origin="DIRECT_FROM_SUPPLIER")
    assert ch.order_id == order.pk and ch.status == "ISSUED" and ch.supplier_invoice_ref == g.number
    assert ch.lines.get().qty == D(200) and ch.lines.get().unit_cost == D("8.00")
    receive(tenant_a, order, [{"kind": "UNPROCESSED_RETURN", "product": raw, "qty": 50}])        # it can be settled like any other
    assert_all_invariants(c)


# --- reversal --------------------------------------------------------------------------------------------

def test_a_receipt_reverses_and_the_material_is_back_at_the_job_worker(tenant_a, method):
    c, raw, fin, sup, order = world(tenant_a, method)
    send(tenant_a, order, raw, 60)
    rc = receive(tenant_a, order, [
        {"kind": "PROCESSED", "product": fin, "qty": 48, "input_product": raw, "input_qty": 50, "charge_amount": 100},
    ])
    out.reverse_receipt(rc, tenant_a.owner, "Wrong count")
    own = InventoryService.default_warehouse(c)
    assert on_hand(c, raw, order.job_worker_warehouse) == D(60) and on_hand(c, fin, own) == 0
    assert JobWorkChallanLine.objects.get().qty_settled == 0
    assert account_net(c, "1400") == 0 and account_net(c, "5410") == 0
    assert_all_invariants(c)
    # It can be received again, correctly.
    receive(tenant_a, order, [{"kind": "PROCESSED", "product": fin, "qty": 49, "input_product": raw, "input_qty": 50}])
    assert on_hand(c, fin, own) == D(49)


def test_goods_that_have_been_sold_cannot_be_taken_back_out(tenant_a, method):
    c, raw, fin, sup, order = world(tenant_a, method)
    send(tenant_a, order, raw, 60)
    rc = receive(tenant_a, order, [{"kind": "PROCESSED", "product": fin, "qty": 48, "input_product": raw, "input_qty": 50}])
    InventoryService.post_movement(
        company=c, product=fin, movement_type="SALE", quantity=D(10), unit_cost=D(12), user=tenant_a.owner,
    )
    with pytest.raises(BusinessRuleError) as exc:
        out.reverse_receipt(rc, tenant_a.owner, "Mistake")
    assert exc.value.get_codes() == "JW_REVERSAL_ORDER"


def test_a_challan_reverses_only_while_nothing_has_been_settled(tenant_a, method):
    c, raw, fin, sup, order = world(tenant_a, method)
    ch = send(tenant_a, order, raw, 60)
    receive(tenant_a, order, [{"kind": "UNPROCESSED_RETURN", "product": raw, "qty": 5}])
    with pytest.raises(BusinessRuleError) as exc:
        out.reverse_challan(ch, tenant_a.owner, "Wrong party")
    assert exc.value.get_codes() == "JW_REVERSAL_ORDER"
    ch2 = send(tenant_a, order, raw, 10)
    out.reverse_challan(ch2, tenant_a.owner, "Wrong party")
    assert on_hand(c, raw, order.job_worker_warehouse) == D(55)
    assert_all_invariants(c)


def test_an_order_closes_only_when_nothing_is_left_out(tenant_a, method):
    c, raw, fin, sup, order = world(tenant_a, method)
    send(tenant_a, order, raw, 10)
    with pytest.raises(BusinessRuleError) as exc:
        out.close_order(order, tenant_a.owner)
    assert exc.value.get_codes() == "JW_STILL_HOLDING"
    receive(tenant_a, order, [{"kind": "UNPROCESSED_RETURN", "product": raw, "qty": 10}])
    assert out.close_order(order, tenant_a.owner).status == "CLOSED"
    with pytest.raises(BusinessRuleError):
        send(tenant_a, order, raw, 1)


# --- ageing and the time limit ---------------------------------------------------------------------------

def test_open_material_is_aged_against_the_one_year_and_three_year_limits(tenant_a, method):
    c, raw, fin, sup, order = world(tenant_a, method)
    tool = stocked(tenant_a, "JW-DIE", 5, 1000)
    today = timezone.localdate()
    a = send(tenant_a, order, raw, 10)
    b = send(tenant_a, order, raw, 10)
    d_ = send(tenant_a, order, raw, 10)
    e = send(tenant_a, order, tool, 2, goods_kind="CAPITAL_GOOD")
    for ch, days in ((a, 100), (b, 310), (d_, 400), (e, 400)):
        JobWorkChallan.objects.filter(pk=ch.pk).update(challan_date=today - timedelta(days=days))
    rows = {(r["challan"], r["product"]): r for r in out.ageing(c, today)}
    assert rows[(a.number, "JW-RAW")]["status"] == "OK"
    assert rows[(b.number, "JW-RAW")]["status"] == "ALERT"                      # 300 days is the alert
    assert rows[(d_.number, "JW-RAW")]["status"] == "OVERDUE"                   # past 365: counts as a supply
    assert rows[(e.number, "JW-DIE")]["status"] == "OK"                         # capital goods have three years
    assert rows[(d_.number, "JW-RAW")]["due_by"] == today - timedelta(days=400) + timedelta(days=365)


def test_the_time_limits_are_settings_not_code(tenant_a, method):
    from manufacturing.services.common import get_settings

    c, raw, fin, sup, order = world(tenant_a, method)
    ch = send(tenant_a, order, raw, 10)
    JobWorkChallan.objects.filter(pk=ch.pk).update(challan_date=timezone.localdate() - timedelta(days=100))
    cfg = get_settings(c)
    cfg.jw_input_limit_days, cfg.jw_input_alert_days = 90, 60
    cfg.save()
    assert out.ageing(c)[0]["status"] == "OVERDUE"


# --- ITC-04 ----------------------------------------------------------------------------------------------

def test_itc04_periods_follow_the_frequency_and_the_due_dates():
    label, frm, to, due = itc04.period("ANNUAL", 2026)
    assert (label, frm, to, due) == ("2026-27", date(2026, 4, 1), date(2027, 3, 31), date(2027, 4, 25))
    h1 = itc04.period("HALF_YEARLY", 2026, 1)
    h2 = itc04.period("HALF_YEARLY", 2026, 2)
    assert (h1[1], h1[2], h1[3]) == (date(2026, 4, 1), date(2026, 9, 30), date(2026, 10, 25))
    assert (h2[1], h2[2], h2[3]) == (date(2026, 10, 1), date(2027, 3, 31), date(2027, 4, 25))
    with pytest.raises(BusinessRuleError):
        itc04.period("HALF_YEARLY", 2026)
    assert itc04.fy_start_year(date(2027, 2, 1)) == 2026 and itc04.fy_start_year(date(2026, 4, 1)) == 2026


def test_itc04_tables_tie_every_return_to_its_challan(tenant_a, method):
    c, raw, fin, sup, order = world(tenant_a, method)
    sup2 = make_supplier(c, name="Shine Finishers", gstin="29CCCCC2222C1Z5")
    other = out.create_order(c, tenant_a.owner, supplier=sup2, process="Finishing")
    ch = send(tenant_a, order, raw, 60)
    receive(tenant_a, order, [
        {"kind": "PROCESSED", "product": fin, "qty": 40, "input_product": raw, "input_qty": 45, "loss_qty": 5},
        {"kind": "UNPROCESSED_RETURN", "product": raw, "qty": 5},
        {"kind": "SENT_TO_OTHER", "product": raw, "qty": 6, "other_order": other.pk},
    ])
    today = timezone.localdate()
    tables = itc04.build(c, today - timedelta(days=1), today + timedelta(days=1))
    assert len(tables["table4"]) == 1                          # the onward challan is not a second sending
    row = tables["table4"][0]
    assert row["challan_no"] == ch.number and row["gstin"] == "29BBBBB1111B1Z5" and row["qty"] == D(60)
    assert row["taxable_value"] == D("600.00") and row["sent_directly_from_supplier"] is False
    assert len(tables["table5a"]) == 2 and len(tables["table5b"]) == 1
    assert {r["orig_challan_no"] for r in tables["table5a"] + tables["table5b"]} == {ch.number}
    assert {r["orig_challan_date"] for r in tables["table5a"]} == {ch.challan_date}
    assert tables["table5b"][0]["sent_to"] == "Shine Finishers"
    assert tables["summary"]["unmatched"] == 0
    csv_text = itc04.to_csv(tables)
    assert "Table 4" in csv_text and ch.number in csv_text


def test_direct_from_supplier_is_flagged_in_table_4(tenant_a, method):
    c, raw, fin, sup, order = world(tenant_a, method)
    g, item = grn(tenant_a, make_supplier(c, name="Yarn Mills"), raw, 20, price="8", warehouse=order.job_worker_warehouse)
    GoodsReceiptService.complete(g, tenant_a.owner)
    g.refresh_from_db()
    today = timezone.localdate()
    row = itc04.build(c, today - timedelta(days=1), today + timedelta(days=1))["table4"][0]
    assert row["sent_directly_from_supplier"] is True and row["supplier_invoice"] == g.number


def test_a_filed_period_is_final(tenant_a, method):
    c, raw, fin, sup, order = world(tenant_a, method)
    send(tenant_a, order, raw, 10)
    today = timezone.localdate()
    label = "T-1"
    filing = itc04.prepare_filing(c, tenant_a.owner, label, today - timedelta(days=30), today + timedelta(days=30))
    assert filing.status == "EXPORTED" and filing.summary["sent_lines"] == 1
    done = itc04.mark_filed(filing, tenant_a.owner, today, "ARN123")
    assert done.status == "FILED" and done.acknowledgement == "ARN123"
    with pytest.raises(BusinessRuleError) as exc:
        itc04.prepare_filing(c, tenant_a.owner, label, today - timedelta(days=30), today + timedelta(days=30))
    assert exc.value.get_codes() == "JW_ITC04_FILED"
    draft = Itc04Filing.objects.create(company=c, period_label="T-2", from_date=today, to_date=today)
    with pytest.raises(BusinessRuleError) as exc:
        itc04.mark_filed(draft, tenant_a.owner, today)
    assert exc.value.get_codes() == "JW_ITC04_NOT_EXPORTED"


# --- job work in: a customer's material ---------------------------------------------------------------------

def principal_world(tenant, method):
    from manufacturing.models import WorkOrderLine

    prepare(tenant, method=method)
    jobwork_on(tenant)
    c = tenant.company
    customer = make_customer(c, name="Anand Textiles")
    cloth = make_product(c, sku="P-CLOTH", name="Grey cloth")
    dyed = make_product(c, sku="P-DYED", name="Dyed cloth")
    dye = stocked(tenant, "P-DYE", 100, 20)
    order = principal.create_order(c, tenant.owner, customer=customer, process="Dyeing")
    principal.receive_material(order, tenant.owner, [{"product": cloth.pk, "qty": 100}], vehicle_no="KA01AB1234")
    bom = make_bom(c, dyed, [(cloth, 1), (dye, 0.1)], user=tenant.owner)
    wo = make_wo(c, bom, 100, user=tenant.owner)
    wo.principal = customer
    wo.save(update_fields=["principal"])
    WorkOrderLine.objects.filter(work_order=wo, component=cloth).update(principal_supplied=True)
    return c, customer, cloth, dyed, dye, order, wo


def test_a_customers_material_is_a_quantity_book_never_stock(tenant_a, method):
    c, customer, cloth, dyed, dye, order, wo = principal_world(tenant_a, method)
    assert principal.balance(c)[0]["qty"] == D(100)
    assert not StockBalance.objects.filter(company=c, product=cloth).exists()          # not in our stock
    assert InventoryValuationService.valuation(c, product=cloth) == []
    ch = JobWorkChallan.objects.get(order=order)
    assert ch.purpose == "Received for job work" and ch.vehicle_no == "KA01AB1234"
    assert_all_invariants(c)


def test_processing_a_customers_material_costs_only_our_own_consumables(tenant_a, method):
    from manufacturing.services import flow, issue as issue_svc, receipt as receipt_svc, release_work_order

    c, customer, cloth, dyed, dye, order, wo = principal_world(tenant_a, method)
    wo = release_work_order(wo, tenant_a.owner)
    issue_svc.post_issue(issue_svc.create_issue(wo, tenant_a.owner), tenant_a.owner)
    wo.refresh_from_db()
    assert wo.cost_issued == D("200.00")                                  # 10 of our dye; the cloth costs us nothing
    assert principal.on_hand(c, customer, cloth) == 0
    rec = receipt_svc.post_receipt(receipt_svc.create_receipt(wo, tenant_a.owner, {"is_final": True}), tenant_a.owner)
    assert rec.total_cost == 0
    assert not StockBalance.objects.filter(company=c, product=dyed).exists()      # the dyed cloth is the customer's
    assert principal.on_hand(c, customer, dyed) == D(100)
    wo.refresh_from_db()
    flow.close_work_order(wo, tenant_a.owner)
    # Our dye is the cost of the service we bill for.
    assert account_net(c, "5400") == D("200.00") and account_net(c, "1450") == 0
    # Send the processed goods back.
    principal.return_material(order, tenant_a.owner, [{"product": dyed.pk, "qty": 100}])
    assert principal.on_hand(c, customer, dyed) == 0
    assert_all_invariants(c)


def test_more_than_the_customer_left_cannot_be_used(tenant_a, method):
    from manufacturing.services import issue as issue_svc, release_work_order

    c, customer, cloth, dyed, dye, order, wo = principal_world(tenant_a, method)
    wo = release_work_order(wo, tenant_a.owner)
    wl = wo.component_lines.get(component=cloth)
    doc = issue_svc.create_issue(wo, tenant_a.owner, [{"wo_line": wl, "qty": 100}])
    issue_svc.post_issue(doc, tenant_a.owner)
    again = issue_svc.create_issue(wo, tenant_a.owner, [{"wo_line": wl, "qty": 5, "extra_reason": "More cloth"}])
    with pytest.raises(BusinessRuleError) as exc:
        issue_svc.post_issue(again, tenant_a.owner)
    assert exc.value.get_codes() == "JW_PRINCIPAL_SHORT"


def test_reversing_an_issue_gives_the_customers_material_back_to_the_book(tenant_a, method):
    from manufacturing.services import issue as issue_svc, release_work_order

    c, customer, cloth, dyed, dye, order, wo = principal_world(tenant_a, method)
    wo = release_work_order(wo, tenant_a.owner)
    doc = issue_svc.post_issue(issue_svc.create_issue(wo, tenant_a.owner), tenant_a.owner)
    issue_svc.reverse_issue(doc, tenant_a.owner, "Wrong order")
    assert principal.on_hand(c, customer, cloth) == D(100)
    assert PrincipalMaterialMovement.objects.filter(kind="CONSUMED", reversed=True).count() == 1
    assert_all_invariants(c)


def test_returning_more_than_is_held_is_refused(tenant_a, method):
    c, customer, cloth, dyed, dye, order, wo = principal_world(tenant_a, method)
    with pytest.raises(BusinessRuleError) as exc:
        principal.return_material(order, tenant_a.owner, [{"product": cloth.pk, "qty": 101}])
    assert exc.value.get_codes() == "JW_PRINCIPAL_SHORT"


def test_waste_in_processing_is_written_off_the_customers_book(tenant_a, method):
    c, customer, cloth, dyed, dye, order, wo = principal_world(tenant_a, method)
    principal.record_loss(order, tenant_a.owner, product=cloth.pk, qty=3, reference="Cutting waste")
    assert principal.on_hand(c, customer, cloth) == D(97)


# --- API --------------------------------------------------------------------------------------------------

def test_job_work_api_is_dark_without_the_flag_and_follows_roles(tenant_a):
    prepare(tenant_a)
    assert tenant_a.client.get("/api/v1/jobwork/orders/").status_code == 404
    jobwork_on(tenant_a)
    assert tenant_a.client.get("/api/v1/jobwork/orders/").status_code == 200
    _u, viewer = member(tenant_a, "VIEWER")
    assert viewer.get("/api/v1/jobwork/ageing/").status_code == 200
    assert viewer.post("/api/v1/jobwork/orders/", {"direction": "OUT", "supplier": 1}, format="json").status_code == 403
    assert tenant_a.staff_client.get("/api/v1/jobwork/orders/").status_code == 403


def test_job_work_api_end_to_end(tenant_a):
    c, raw, fin, sup, _order = world(tenant_a, "WAVG")
    api = tenant_a.client
    order = api.post("/api/v1/jobwork/orders/", {"direction": "OUT", "supplier": sup.pk, "process": "Dyeing"}, format="json")
    assert order.status_code == 201, order.data
    oid = body(order)["id"]
    ch = api.post("/api/v1/jobwork/challans/", {"order": oid, "lines": [{"product": raw.pk, "qty": "40"}]}, format="json")
    assert ch.status_code == 201, ch.data
    cid = body(ch)["id"]
    issued = api.post(f"/api/v1/jobwork/challans/{cid}/issue/", format="json", HTTP_IDEMPOTENCY_KEY="i1")
    assert issued.status_code == 200 and body(issued)["status"] == "ISSUED"
    api.post(f"/api/v1/jobwork/challans/{cid}/issue/", format="json", HTTP_IDEMPOTENCY_KEY="i1")
    assert JobWorkChallan.objects.filter(status="ISSUED").count() == 1
    rc = api.post("/api/v1/jobwork/receipts/", {"order": oid, "lines": [
        {"kind": "PROCESSED", "product": fin.pk, "qty": "38", "input_product": raw.pk, "input_qty": "40", "charge_amount": "80"},
    ]}, format="json")
    assert rc.status_code == 201, rc.data
    posted = api.post(f"/api/v1/jobwork/receipts/{body(rc)['id']}/post/", format="json")
    assert posted.status_code == 200 and D(body(posted)["lines"][0]["cost_amount"]) == D("480.00")
    assert body(api.get("/api/v1/jobwork/balance/"))["at_job_workers"] == []
    assert api.get("/api/v1/jobwork/ageing/").status_code == 200
    today = timezone.localdate()
    itc = api.get(f"/api/v1/jobwork/itc04/?from={today - timedelta(days=1)}&to={today + timedelta(days=1)}")
    assert itc.status_code == 200 and len(body(itc)["table4"]) == 1
    csv = api.get(f"/api/v1/jobwork/itc04/?from={today}&to={today}&export=csv")
    assert csv.status_code == 200 and b"Table 4" in csv.content
    close = api.post(f"/api/v1/jobwork/orders/{oid}/close/", format="json")
    assert close.status_code == 200 and body(close)["status"] == "CLOSED"


def test_only_the_tax_roles_prepare_and_file_itc04(tenant_a):
    c, raw, fin, sup, order = world(tenant_a, "WAVG")
    _u, inv = member(tenant_a, "INVENTORY_STAFF", can_manage_inventory=True)
    _a, acc = member(tenant_a, "ACCOUNTANT")
    assert inv.post("/api/v1/jobwork/itc04-filings/prepare/", {"fy": 2026}, format="json").status_code == 403
    prepared = acc.post("/api/v1/jobwork/itc04-filings/prepare/", {"fy": 2026}, format="json")
    assert prepared.status_code == 201 and body(prepared)["period_label"] == "2026-27"
    fid = body(prepared)["id"]
    assert inv.post(f"/api/v1/jobwork/itc04-filings/{fid}/mark-filed/", {}, format="json").status_code == 403
    assert acc.post(f"/api/v1/jobwork/itc04-filings/{fid}/mark-filed/", {"acknowledgement": "A1"}, format="json").status_code == 200
    due = acc.get("/api/v1/jobwork/itc04-filings/due/")
    assert due.status_code == 200 and body(due)["frequency"] == "ANNUAL"
    # Inventory staff do send and receive.
    ch = inv.post("/api/v1/jobwork/challans/", {"order": order.pk, "lines": [{"product": raw.pk, "qty": "5"}]}, format="json")
    assert ch.status_code == 201
