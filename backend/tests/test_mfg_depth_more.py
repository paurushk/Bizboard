"""Depth tests (phase 1 of the test plan), second batch: a customer's goods coming back out, the work order form,
the tablet's stoppages, and the outside-step rules."""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.exceptions import BusinessRuleError
from core.invariants import assert_all_invariants
from jobwork.services import principal
from manufacturing.models import Bom, DowntimeEvent, DowntimeReason, WorkCentre, WorkOrder
from manufacturing.services import issue as issue_svc
from manufacturing.services import receipt as receipt_svc
from manufacturing.services import release_work_order, shopfloor
from tests.conftest import make_product, make_supplier
from tests.mfg_helpers import make_bom, make_wo, member, prepare, stocked
from tests.test_mfg_jobwork import principal_world

pytestmark = pytest.mark.django_db

M = "/api/v1/manufacturing"


def D(v):
    return Decimal(str(v))


@pytest.fixture(params=["WAVG", "FIFO"])
def method(request):
    return request.param


def code(exc):
    return exc.value.get_codes()


def data_of(resp):
    return json.loads(resp.content)["data"]


# --- processing a customer's material: undoing and refusing -------------------------------------------------------------

def finished_for_customer(tenant, method):
    c, customer, cloth, dyed, dye, order, wo = principal_world(tenant, method)
    wo = release_work_order(wo, tenant.owner)
    issue_svc.post_issue(issue_svc.create_issue(wo, tenant.owner), tenant.owner)
    rec = receipt_svc.post_receipt(receipt_svc.create_receipt(wo, tenant.owner, {"is_final": True}), tenant.owner)
    wo.refresh_from_db()
    return c, customer, dyed, order, wo, rec


def test_a_receipt_for_a_customers_job_can_be_reversed_before_the_goods_go_back(tenant_a, method):
    c, customer, dyed, order, wo, rec = finished_for_customer(tenant_a, method)
    assert principal.on_hand(c, customer, dyed) == D(100) and wo.status == WorkOrder.Status.COMPLETED
    undone = receipt_svc.reverse_receipt(rec, tenant_a.owner, "counted wrong")
    wo.refresh_from_db()
    assert undone.status == "REVERSED" and principal.on_hand(c, customer, dyed) == 0
    assert wo.qty_completed == 0 and wo.status == WorkOrder.Status.IN_PROGRESS and wo.completed_at is None
    assert_all_invariants(c)


def test_goods_already_sent_back_to_the_customer_cannot_be_taken_out_of_the_books_again(tenant_a, method):
    c, customer, dyed, order, wo, rec = finished_for_customer(tenant_a, method)
    principal.return_material(order, tenant_a.owner, [{"product": dyed.pk, "qty": 100}])
    with pytest.raises(BusinessRuleError) as exc:
        receipt_svc.reverse_receipt(rec, tenant_a.owner, "too late")
    assert code(exc) == "MFG_REVERSAL_ORDER"
    assert principal.on_hand(c, customer, dyed) == 0


def test_a_customers_job_makes_only_the_processed_goods(tenant_a, method):
    c, customer, cloth, dyed, dye, order, wo = principal_world(tenant_a, method)
    wo = release_work_order(wo, tenant_a.owner)
    issue_svc.post_issue(issue_svc.create_issue(wo, tenant_a.owner), tenant_a.owner)
    scrap = make_product(c, sku="P-SCRAP")
    rec = receipt_svc.create_receipt(wo, tenant_a.owner, {"is_final": True, "lines": [
        {"kind": "MAIN", "qty_good": 90}, {"kind": "BY_PRODUCT", "product": scrap, "qty_good": 5},
    ]})
    with pytest.raises(BusinessRuleError) as exc:
        receipt_svc.post_receipt(rec, tenant_a.owner)
    assert code(exc) == "MFG_BAD_OUTPUT"


# --- the work order form ------------------------------------------------------------------------------------------------

def test_the_work_order_form_checks_quantity_and_priority_and_numbers_the_order(tenant_a):
    company = prepare(tenant_a, separate=True)
    raw = stocked(tenant_a, "WF-RAW", 100, 5)
    fg = make_product(company, sku="WF-FG")
    bom = make_bom(company, fg, [(raw, 1)], user=tenant_a.owner)
    c = tenant_a.client
    assert c.post(f"{M}/work-orders/", {"bom": bom.pk, "qty": "0"}, format="json").status_code == 400
    assert c.post(f"{M}/work-orders/", {"bom": bom.pk, "qty": "5", "priority": 9}, format="json").status_code == 400
    made = c.post(f"{M}/work-orders/", {"bom": bom.pk, "qty": "5", "priority": 2, "dueDate": str(timezone.localdate() + timedelta(days=5))}, format="json")
    assert made.status_code == 201, made.content[:300]
    wo = data_of(made)
    assert wo["number"].startswith("WO-") and wo["issueMode"] == "SEPARATE" and wo["status"] == "DRAFT" and wo["priority"] == 2
    assert len(wo["componentLines"]) == 1


def test_a_draft_order_takes_serials_and_lots_for_its_lines_but_a_released_one_only_moves_its_plan(tenant_a):
    company = prepare(tenant_a, separate=True)
    raw = stocked(tenant_a, "WF2-RAW", 100, 5)
    fg = make_product(company, sku="WF2-FG")
    bom = make_bom(company, fg, [(raw, 1)], user=tenant_a.owner)
    c = tenant_a.client
    wo = data_of(c.post(f"{M}/work-orders/", {"bom": bom.pk, "qty": "5"}, format="json"))
    line = wo["componentLines"][0]
    patched = c.patch(f"{M}/work-orders/{wo['id']}/", {
        "qty": "6", "componentLines": [{"id": line["id"], "serialNumbers": ["A", "B"], "lotAllocations": []}],
    }, format="json")
    assert patched.status_code == 200, patched.content[:300]
    assert data_of(patched)["qty"] in ("6", "6.000")
    assert c.post(f"{M}/work-orders/{wo['id']}/release/", {}, format="json").status_code == 200
    moved = c.patch(f"{M}/work-orders/{wo['id']}/", {"qty": "999", "priority": 1, "notes": "rush"}, format="json")
    assert moved.status_code == 200
    got = data_of(moved)
    assert got["priority"] == 1 and got["notes"] == "rush" and got["qty"] in ("6", "6.000")        # the quantity did not move


def test_a_recipe_moves_between_states_through_its_status_field(tenant_a):
    company = prepare(tenant_a)
    raw = stocked(tenant_a, "WF3-RAW", 100, 5)
    fg = make_product(company, sku="WF3-FG")
    bom = make_bom(company, fg, [(raw, 1)], user=tenant_a.owner, status="DRAFT")
    c = tenant_a.client
    up = c.patch(f"{M}/boms/{bom.pk}/", {"status": "ACTIVE"}, format="json")
    assert up.status_code == 200 and data_of(up)["status"] == "ACTIVE"
    down = c.patch(f"{M}/boms/{bom.pk}/", {"status": "ARCHIVED"}, format="json")
    assert down.status_code == 200 and data_of(down)["status"] == "ARCHIVED"
    assert Bom.objects.get(pk=bom.pk).status == "ARCHIVED"


# --- the tablet's stoppages ---------------------------------------------------------------------------------------------

def tablet_for(tenant, **extra):
    company = prepare(tenant)
    flags = dict(company.feature_flags or {})
    flags["MFG_SHOP_FLOOR"] = True
    company.feature_flags = flags
    company.save(update_fields=["feature_flags"])
    centre = WorkCentre.objects.create(company=company, code="TD", name="Bench")
    reason = DowntimeReason.objects.create(company=company, code="JAM", name="Jam")
    shopfloor.create_operator(company, tenant.owner, code="TD1", name="Asha", pin="4821")
    tablet = APIClient()
    token = json.loads(tablet.post(f"{M}/tablet/login/", {"company": company.pk, "code": "TD1", "pin": "4821"}, format="json").content)["data"]["token"]
    return company, centre, reason, tablet, {"HTTP_X_OPERATOR_TOKEN": token}


def test_an_operator_stops_and_restarts_a_work_centre_from_the_tablet(tenant_a):
    company, centre, reason, tablet, hdr = tablet_for(tenant_a)
    began = timezone.now() - timedelta(minutes=30)
    start = tablet.post(f"{M}/tablet/downtime/start/", {"work_centre": centre.pk, "reason": reason.pk, "notes": "belt", "occurred_at": began.isoformat()}, format="json", HTTP_IDEMPOTENCY_KEY="td-1", **hdr)
    assert start.status_code == 200, start.content[:300]
    event = DowntimeEvent.objects.get(company=company)
    assert abs((event.started_at - began).total_seconds()) < 1 and "Asha: belt" in event.notes
    body = {"work_centre": centre.pk, "reason": reason.pk, "notes": "belt", "occurred_at": began.isoformat()}
    again = tablet.post(f"{M}/tablet/downtime/start/", body, format="json", HTTP_IDEMPOTENCY_KEY="td-1", **hdr)
    assert again.status_code == 200
    changed = tablet.post(f"{M}/tablet/downtime/start/", {**body, "notes": "other"}, format="json", HTTP_IDEMPOTENCY_KEY="td-1", **hdr)
    assert changed.status_code == 422                                                                    # one key, a different tap: refused and DowntimeEvent.objects.filter(company=company).count() == 1     # a resent tap is not a second stoppage
    second = tablet.post(f"{M}/tablet/downtime/start/", {"work_centre": centre.pk, "reason": reason.pk}, format="json", **hdr)
    assert second.status_code == 400                                                                      # one is already open
    end = tablet.post(f"{M}/tablet/downtime/end/", {"event": event.pk}, format="json", HTTP_IDEMPOTENCY_KEY="td-2", **hdr)
    assert end.status_code == 200 and D(data_of(end)["minutes"]) >= 29
    assert tablet.post(f"{M}/tablet/downtime/end/", {"event": event.pk}, format="json", **hdr).status_code == 400   # already ended


def test_the_tablet_refuses_unknown_things_in_a_stoppage(tenant_a):
    company, centre, reason, tablet, hdr = tablet_for(tenant_a)
    assert tablet.post(f"{M}/tablet/downtime/start/", {"work_centre": 999999, "reason": reason.pk}, format="json", **hdr).status_code == 400
    assert tablet.post(f"{M}/tablet/downtime/start/", {"work_centre": centre.pk, "reason": 999999}, format="json", **hdr).status_code == 400
    assert tablet.post(f"{M}/tablet/downtime/start/", {"work_centre": "abc", "reason": reason.pk}, format="json", **hdr).status_code == 400
    assert tablet.post(f"{M}/tablet/downtime/end/", {"event": 999999}, format="json", **hdr).status_code == 404
    assert tablet.post(f"{M}/tablet/downtime/pause/", {}, format="json", **hdr).status_code == 404
    DowntimeReason.objects.filter(pk=reason.pk).update(is_active=False)
    assert tablet.post(f"{M}/tablet/downtime/start/", {"work_centre": centre.pk, "reason": reason.pk}, format="json", **hdr).status_code == 400
    assert tablet.post(f"{M}/tablet/downtime/start/", {"work_centre": centre.pk, "reason": reason.pk}, format="json").status_code == 403   # no token


# --- sending a step out: what is refused ------------------------------------------------------------------------------

def outside_world(tenant, method="WAVG"):
    from manufacturing.services import subcontract  # noqa: F401

    company = prepare(tenant, method=method)
    flags = dict(company.feature_flags or {})
    flags.update({"MFG_JOB_WORK": True, "MFG_SHOP_FLOOR": True})
    company.feature_flags = flags
    company.save(update_fields=["feature_flags"])
    centre = WorkCentre.objects.create(company=company, code="OSW", name="Outside", kind="OUTSIDE")
    raw = stocked(tenant, "OS-RAW", 100, 10)
    part = make_product(company, sku="OS-PART")
    fg = make_product(company, sku="OS-FG")
    bom = make_bom(company, fg, [(part, 1)], user=tenant.owner)
    return company, centre, raw, part, bom


def test_a_step_cannot_be_sent_without_a_job_worker_or_material_or_once_the_order_is_over(tenant_a):
    from manufacturing.models import JobCard
    from manufacturing.services import flow, subcontract

    company, centre, raw, part, bom = outside_world(tenant_a)
    shopfloor.set_routing(bom, [{"sequence": 10, "name": "Plate", "work_centre": centre, "is_subcontract": True}], tenant_a.owner)
    wo = release_work_order(make_wo(company, bom, 10, user=tenant_a.owner), tenant_a.owner)
    card = shopfloor.create_job_cards(wo, tenant_a.owner)[0]
    with pytest.raises(BusinessRuleError) as exc:
        subcontract.send_out(card, tenant_a.owner, lines=[{"product": raw.pk, "qty": 1}])
    assert code(exc) == "MFG_SUBCONTRACT_NO_WORKER"                                  # the step names no job worker
    sup = make_supplier(company, name="Late Worker")
    JobCard.objects.filter(pk=card.pk).update(status="DONE")
    card.refresh_from_db()
    with pytest.raises(BusinessRuleError) as exc:
        subcontract.send_out(card, tenant_a.owner, supplier=sup, lines=[{"product": raw.pk, "qty": 1}])
    assert code(exc) == "MFG_CARD_DONE"
    JobCard.objects.filter(pk=card.pk).update(status="PLANNED")
    flow.cancel_separate(wo, tenant_a.owner)
    card.refresh_from_db()
    with pytest.raises(BusinessRuleError) as exc:
        subcontract.send_out(card, tenant_a.owner, supplier=sup, lines=[{"product": raw.pk, "qty": 1}])
    assert code(exc) == "MFG_BAD_WO_STATUS"


def test_closing_an_order_after_part_of_the_work_came_back_finishes_the_step(tenant_a):
    from jobwork.services import out
    from manufacturing.models import JobCard
    from manufacturing.services import subcontract

    company, centre, raw, part, bom = outside_world(tenant_a)
    sup = make_supplier(company, name="Half Worker")
    shopfloor.set_routing(bom, [{"sequence": 10, "name": "Plate", "work_centre": centre, "is_subcontract": True, "subcontract_supplier": sup.pk}], tenant_a.owner)
    wo = release_work_order(make_wo(company, bom, 10, user=tenant_a.owner), tenant_a.owner)
    card = shopfloor.create_job_cards(wo, tenant_a.owner)[0]
    order, challan = subcontract.send_out(card, tenant_a.owner, lines=[{"product": raw.pk, "qty": 10}], issue=True)
    rc = out.create_receipt(order, tenant_a.owner, [
        {"kind": "PROCESSED", "product": part.pk, "qty": 6, "input_product": raw.pk, "input_qty": 6},
        {"kind": "UNPROCESSED_RETURN", "product": raw.pk, "qty": 4},
    ])
    out.post_receipt(rc, tenant_a.owner)
    card = JobCard.objects.get(pk=card.pk)
    assert card.status == "DONE" and card.qty_good == D(6)                     # everything sent is accounted for
    out.close_order(order, tenant_a.owner)
    assert JobCard.objects.get(pk=card.pk).status == "DONE"                    # closing does not undo finished work
    assert_all_invariants(company)


def test_the_outside_step_screens_follow_the_job_work_switch_and_the_card_must_be_the_companys_own(tenant_a, tenant_b):
    company, centre, raw, part, bom = outside_world(tenant_a)
    shopfloor.set_routing(bom, [{"sequence": 10, "name": "Plate", "work_centre": centre, "is_subcontract": True}], tenant_a.owner)
    wo = release_work_order(make_wo(company, bom, 10, user=tenant_a.owner), tenant_a.owner)
    card = shopfloor.create_job_cards(wo, tenant_a.owner)[0]
    stranger = tenant_b.client
    assert stranger.get(f"{M}/job-cards/{card.pk}/subcontract-defaults/").status_code in (403, 404)
    assert stranger.post(f"{M}/job-cards/{card.pk}/subcontract/", {}, format="json").status_code in (403, 404)
    bad = tenant_a.client.post(f"{M}/job-cards/{card.pk}/subcontract/", {"supplier": 999999, "lines": [{"product": raw.pk, "qty": "1"}]}, format="json")
    assert bad.status_code == 400
    _u, auditor = member(tenant_a, "AUDITOR")
    assert auditor.post(f"{M}/job-cards/{card.pk}/subcontract/", {}, format="json").status_code == 403
