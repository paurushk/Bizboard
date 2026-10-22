"""QOS-0147: a routing step done by a job worker, raised from the work order and written back by the receipt."""

from decimal import Decimal

import pytest

from core.exceptions import BusinessRuleError
from core.invariants import assert_all_invariants
from jobwork.models import JobWorkOrder
from jobwork.services import out
from manufacturing.models import JobCard, MaterialIssue, WorkCentre, WorkOrder
from manufacturing.services import flow, issue as issue_svc, release_work_order, shopfloor, subcontract
from tests.conftest import make_product, make_supplier
from tests.mfg_helpers import body, make_bom, make_wo, member, prepare, stocked

pytestmark = pytest.mark.django_db


def D(v):
    return Decimal(str(v))


@pytest.fixture(params=["WAVG", "FIFO"])
def method(request):
    return request.param


def world(tenant, method, qty=100):
    company = prepare(tenant, method=method)
    flags = dict(company.feature_flags or {})
    flags.update({"MFG_JOB_WORK": True, "MFG_SHOP_FLOOR": True})
    company.feature_flags = flags
    company.save(update_fields=["feature_flags"])
    centre = WorkCentre.objects.create(company=company, code="PLT", name="Plating", kind="OUTSIDE")
    sup = make_supplier(company, name="Shine Platers", gstin="29BBBBB1111B1Z5")
    raw = stocked(tenant, "SC-RAW", 200, 10)
    part = make_product(company, sku="SC-PART", name="Plated part")
    fg = make_product(company, sku="SC-FG", name="Assembly")
    bom = make_bom(company, fg, [(part, 1)], user=tenant.owner)
    shopfloor.set_routing(bom, [
        {"sequence": 10, "name": "Plating", "work_centre": centre, "is_subcontract": True, "subcontract_supplier": sup.pk},
    ], tenant.owner)
    wo = release_work_order(make_wo(company, bom, qty, user=tenant.owner), tenant.owner)
    card = shopfloor.create_job_cards(wo, tenant.owner)[0]
    return company, raw, part, fg, sup, wo, card


def goods_back(tenant, order, raw, part, qty=100, charge=500):
    rc = out.create_receipt(order, tenant.owner, [{
        "kind": "PROCESSED", "product": part.pk, "qty": qty, "input_product": raw.pk, "input_qty": qty,
        "charge_amount": charge,
    }])
    return out.post_receipt(rc, tenant.owner)


def test_raising_job_work_for_a_step_links_the_order_and_waits_for_the_challan(tenant_a, method):
    company, raw, part, fg, sup, wo, card = world(tenant_a, method)
    order, challan = subcontract.send_out(card, tenant_a.owner, lines=[{"product": raw.pk, "qty": 100}])
    card.refresh_from_db()
    assert order.work_order_id == wo.pk and order.job_card_id == card.pk and order.supplier_id == sup.pk
    assert order.process == "Plating" and card.jobwork_order_id == order.pk
    assert challan.status == "DRAFT" and card.status == "PLANNED"
    with pytest.raises(BusinessRuleError) as exc:
        subcontract.send_out(card, tenant_a.owner, lines=[{"product": raw.pk, "qty": 1}])
    assert exc.value.get_codes() == "MFG_SUBCONTRACT_RAISED"


def test_a_factory_step_cannot_be_sent_out(tenant_a, method):
    company, raw, part, fg, sup, wo, card = world(tenant_a, method)
    JobCard.objects.filter(pk=card.pk).update(is_subcontract=False)
    card.refresh_from_db()
    with pytest.raises(BusinessRuleError) as exc:
        subcontract.send_out(card, tenant_a.owner, lines=[{"product": raw.pk, "qty": 1}])
    assert exc.value.get_codes() == "MFG_SUBCONTRACT_NOT_STEP"


def test_the_whole_round_trip_writes_back_to_the_card_and_drafts_the_issue(tenant_a, method):
    company, raw, part, fg, sup, wo, card = world(tenant_a, method)
    order, challan = subcontract.send_out(card, tenant_a.owner, lines=[{"product": raw.pk, "qty": 100}], issue=True)
    card.refresh_from_db()
    wo.refresh_from_db()
    assert card.status == "IN_PROGRESS" and wo.status == WorkOrder.Status.IN_PROGRESS and card.started_at
    # the order cannot finish or be cancelled while the step is out
    for call in (lambda: flow.complete_separate(wo, tenant_a.owner), lambda: flow.cancel_separate(wo, tenant_a.owner)):
        with pytest.raises(BusinessRuleError) as exc:
            call()
        assert exc.value.get_codes() == "MFG_SUBCONTRACT_OPEN"
    rc = goods_back(tenant_a, order, raw, part)
    card.refresh_from_db()
    assert card.status == "DONE" and card.qty_good == D(100) and card.outside_cost == D("500.00") and card.finished_at
    draft = MaterialIssue.objects.get(work_order=wo)
    assert draft.status == "DRAFT" and draft.notes == f"From job work receipt {rc.number}"
    assert draft.lines.get().qty == D(100) and draft.lines.get().component_id == part.pk
    posted = issue_svc.post_issue(draft, tenant_a.owner)
    wo.refresh_from_db()
    assert posted.lines.get().cost_amount == D("1500.00")           # 100 x (10 of raw + 5 of job charge)
    assert wo.cost_issued == D("1500.00")                           # the charge came in through the goods, once
    assert_all_invariants(company)


def test_reversing_the_receipt_reopens_the_step_and_drops_the_draft(tenant_a, method):
    company, raw, part, fg, sup, wo, card = world(tenant_a, method)
    order, _ = subcontract.send_out(card, tenant_a.owner, lines=[{"product": raw.pk, "qty": 100}], issue=True)
    rc = goods_back(tenant_a, order, raw, part)
    assert MaterialIssue.objects.filter(work_order=wo).count() == 1
    out.reverse_receipt(rc, tenant_a.owner, "wrong count")
    card.refresh_from_db()
    assert card.status == "IN_PROGRESS" and card.qty_good == 0 and card.outside_cost == 0 and card.finished_at is None
    assert MaterialIssue.objects.filter(work_order=wo).count() == 0


def test_a_part_delivery_leaves_the_step_open(tenant_a, method):
    company, raw, part, fg, sup, wo, card = world(tenant_a, method)
    order, _ = subcontract.send_out(card, tenant_a.owner, lines=[{"product": raw.pk, "qty": 100}], issue=True)
    goods_back(tenant_a, order, raw, part, qty=40, charge=200)
    card.refresh_from_db()
    assert card.status == "IN_PROGRESS" and card.qty_good == D(40)
    goods_back(tenant_a, order, raw, part, qty=60, charge=300)
    card.refresh_from_db()
    assert card.status == "DONE" and card.qty_good == D(100) and card.outside_cost == D("500.00")


def test_closing_an_empty_order_lets_the_step_be_raised_again(tenant_a, method):
    company, raw, part, fg, sup, wo, card = world(tenant_a, method)
    order, challan = subcontract.send_out(card, tenant_a.owner, lines=[{"product": raw.pk, "qty": 100}], issue=True)
    out.reverse_challan(challan, tenant_a.owner, "sent to the wrong place")
    out.close_order(order, tenant_a.owner)
    card.refresh_from_db()
    assert card.status == "PLANNED" and card.jobwork_order_id is None
    again, _ = subcontract.send_out(card, tenant_a.owner, lines=[{"product": raw.pk, "qty": 100}])
    assert again.pk != order.pk


def test_default_lines_are_the_material_the_order_still_has_to_take(tenant_a, method):
    company, raw, part, fg, sup, wo, card = world(tenant_a, method)
    assert subcontract.default_lines(wo) == [{"product": part.pk, "qty": D(100)}]


def test_api_raises_the_job_work_and_follows_roles_and_the_flag(tenant_a):
    company, raw, part, fg, sup, wo, card = world(tenant_a, "WAVG")
    base = f"/api/v1/manufacturing/job-cards/{card.pk}"
    _i, floor = member(tenant_a, "INVENTORY_STAFF", can_manage_inventory=True)
    defaults = floor.get(f"{base}/subcontract-defaults/")
    assert defaults.status_code == 200 and body(defaults)["supplier"] == sup.pk
    sent = floor.post(f"{base}/subcontract/", {
        "lines": [{"product": raw.pk, "qty": "100"}], "vehicleNo": "KA01AB1234", "issue": True,
    }, format="json", HTTP_IDEMPOTENCY_KEY="sc-1")
    assert sent.status_code == 201, sent.data
    data = body(sent)
    assert data["order"]["work_order_id"] == wo.pk and data["challan"]["status"] == "ISSUED"
    assert data["card"]["status"] == "IN_PROGRESS" and data["card"]["jobwork_order_id"] == data["order"]["id"]
    assert JobWorkOrder.objects.get(pk=data["order"]["id"]).job_card_id == card.pk
    again = floor.post(f"{base}/subcontract/", {"lines": [{"product": raw.pk, "qty": "1"}]}, format="json", HTTP_IDEMPOTENCY_KEY="sc-2")
    assert again.status_code == 400 and "MFG_SUBCONTRACT_RAISED" in str(again.data)
    company.feature_flags = {**company.feature_flags, "MFG_JOB_WORK": False}
    company.save(update_fields=["feature_flags"])
    assert floor.get(f"{base}/subcontract-defaults/").status_code == 404


def test_an_item_that_is_not_one_of_the_orders_materials_comes_back_as_an_extra_material_draft(tenant_a, method):
    company, raw, part, fg, sup, wo, card = world(tenant_a, method)
    stray = make_product(company, sku="SC-STRAY", name="Plated washer")
    order, _ = subcontract.send_out(card, tenant_a.owner, lines=[{"product": raw.pk, "qty": 10}], issue=True)
    rc = out.create_receipt(order, tenant_a.owner, [{
        "kind": "PROCESSED", "product": stray.pk, "qty": 10, "input_product": raw.pk, "input_qty": 10, "charge_amount": 50,
    }])
    rc = out.post_receipt(rc, tenant_a.owner)
    draft = MaterialIssue.objects.get(work_order=wo)
    line = draft.lines.get()
    assert draft.status == "DRAFT" and line.component_id == stray.pk and line.wo_line_id is None
    assert line.extra_reason == f"Returned from job worker ({rc.number})"
    # a floor user cannot post it, a manager can
    with pytest.raises(BusinessRuleError) as exc:
        issue_svc.post_issue(draft, tenant_a.owner, is_manager=False)
    assert exc.value.get_codes() == "MFG_EXTRA_NEEDS_MANAGER"
    issue_svc.post_issue(draft, tenant_a.owner, is_manager=True)
    wo.refresh_from_db()
    assert wo.cost_issued == D("150.00")                            # 10 x (10 of raw + 5 of job charge)
    assert_all_invariants(company)
