"""Manufacturing phase 6: routing, job cards, time and cost, downtime, load, maintenance, tablet sign-in."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.exceptions import BusinessRuleError
from core.invariants import assert_all_invariants
from manufacturing.models import (
    DowntimeEvent, DowntimeReason, JobCard, Machine, MaintenancePlan, Operator, TimeLog, WorkCentre, WorkOrder,
)
from manufacturing.services import issue as issue_svc, receipt as receipt_svc, release_work_order, shopfloor
from tests.conftest import make_product
from tests.mfg_helpers import account_net, body, make_bom, make_wo, member, prepare, stocked

pytestmark = pytest.mark.django_db


def D(v):
    return Decimal(str(v))


@pytest.fixture
def noon_today():
    """Time logs are filed under the day they started, so a test that reads them by date must not run across midnight.

    Used only where needed: freezing the clock also freezes the request throttle timer, which breaks the tablet login.
    """
    from datetime import datetime

    from freezegun import freeze_time

    today = timezone.localdate()
    noon = timezone.make_aware(datetime(today.year, today.month, today.day, 12, 0))
    with freeze_time(noon, tick=True):
        yield


@pytest.fixture(params=["WAVG", "FIFO"])
def method(request):
    return request.param


def floor_on(tenant, costing=False):
    flags = dict(tenant.company.feature_flags or {})
    flags["MFG_SHOP_FLOOR"] = True
    if costing:
        flags["MFG_COSTING_GL"] = True
    tenant.company.feature_flags = flags
    tenant.company.save(update_fields=["feature_flags"])


def centres(tenant):
    c = tenant.company
    cut = WorkCentre.objects.create(company=c, code="CUT", name="Cutting", labour_rate=D(120), machine_rate=D(300), overhead_rate=D(60), hours_per_day=D(8))
    sew = WorkCentre.objects.create(company=c, code="SEW", name="Stitching", labour_rate=D(100), hours_per_day=D(8))
    return cut, sew


def routed(tenant, method, qty=100, costing=False):
    company = prepare(tenant, method=method, costing_gl=costing)
    floor_on(tenant, costing)
    cut, sew = centres(tenant)
    fg = make_product(company, sku="SF-FG")
    comp = stocked(tenant, "SF-C", 1000, 10)
    bom = make_bom(company, fg, [(comp, 1)], user=tenant.owner)
    shopfloor.set_routing(bom, [
        {"sequence": 10, "name": "Cut", "work_centre": cut, "setup_minutes": 30, "run_minutes_per_unit": D("0.5")},
        {"sequence": 20, "name": "Stitch", "work_centre": sew, "setup_minutes": 0, "run_minutes_per_unit": D("1")},
    ], tenant.owner)
    wo = release_work_order(make_wo(company, bom, qty, user=tenant.owner), tenant.owner)
    cards = shopfloor.create_job_cards(wo, tenant.owner)
    return company, fg, comp, cut, sew, bom, wo, cards


def backdate_open_log(card, minutes):
    TimeLog.objects.filter(job_card=card, ended_at__isnull=True).update(started_at=timezone.now() - timedelta(minutes=minutes))


# --- routing and job cards ---------------------------------------------------------------------------

def test_a_routing_gives_each_order_a_job_card_per_operation(tenant_a, method):
    company, fg, comp, cut, sew, bom, wo, cards = routed(tenant_a, method)
    assert [(c.name, c.sequence) for c in cards] == [("Cut", 10), ("Stitch", 20)]
    assert cards[0].planned_minutes == D("80.00") and cards[1].planned_minutes == D("100.00")      # 30 + 100 x 0.5; 100 x 1
    assert cards[0].qty_planned == D(100) and cards[0].status == "PLANNED"
    assert len(shopfloor.create_job_cards(wo, tenant_a.owner)) == 2                               # asking again adds none
    assert JobCard.objects.count() == 2


def test_a_routing_is_read_only_once_an_order_has_used_the_recipe(tenant_a, method):
    company, fg, comp, cut, sew, bom, wo, cards = routed(tenant_a, method)
    with pytest.raises(BusinessRuleError) as exc:
        shopfloor.set_routing(bom, [{"sequence": 10, "name": "x", "work_centre": cut}], tenant_a.owner)
    assert exc.value.get_codes() == "MFG_BOM_LOCKED"


def test_two_operations_cannot_share_a_sequence_number(tenant_a):
    company = prepare(tenant_a)
    floor_on(tenant_a)
    cut, sew = centres(tenant_a)
    bom = make_bom(company, make_product(company, sku="SQ-FG"), [(stocked(tenant_a, "SQ-C", 1, 1), 1)], user=tenant_a.owner)
    with pytest.raises(BusinessRuleError) as exc:
        shopfloor.set_routing(bom, [{"sequence": 10, "work_centre": cut}, {"sequence": 10, "work_centre": sew}], tenant_a.owner)
    assert exc.value.get_codes() == "MFG_BAD_SEQUENCE"


# --- running a card -------------------------------------------------------------------------------------

def test_start_pause_and_finish_keep_time_and_move_the_order_along(tenant_a, method):
    company, fg, comp, cut, sew, bom, wo, cards = routed(tenant_a, method)
    card = cards[0]
    shopfloor.start_card(card, user=tenant_a.owner)
    shopfloor.start_card(card, user=tenant_a.owner)                                   # a second tap changes nothing
    assert TimeLog.objects.filter(job_card=card).count() == 1
    wo.refresh_from_db()
    assert wo.status == "IN_PROGRESS"
    backdate_open_log(card, 40)
    shopfloor.pause_card(card, user=tenant_a.owner)
    card.refresh_from_db()
    assert card.status == "PAUSED" and card.minutes_worked == D("40.00")
    shopfloor.start_card(card, user=tenant_a.owner)
    backdate_open_log(card, 50)
    done = shopfloor.finish_card(card, qty_good=95, qty_rejected=5, user=tenant_a.owner)
    assert done.status == "DONE" and done.minutes_worked == D("90.00") and done.qty_good == 95 and done.qty_rejected == 5
    assert done.finished_at is not None


def test_partial_counts_add_up_without_stopping_the_clock(tenant_a, method):
    company, fg, comp, cut, sew, bom, wo, cards = routed(tenant_a, method)
    card = cards[0]
    shopfloor.start_card(card, user=tenant_a.owner)
    shopfloor.report_card(card, qty_good=30, qty_rejected=1, user=tenant_a.owner)
    shopfloor.report_card(card, qty_good=20, user=tenant_a.owner)
    card.refresh_from_db()
    assert (card.qty_good, card.qty_rejected, card.status) == (D(50), D(1), "IN_PROGRESS")
    with pytest.raises(BusinessRuleError):
        shopfloor.report_card(card, qty_good=-1)


def test_a_finished_card_cannot_be_started_again(tenant_a, method):
    company, fg, comp, cut, sew, bom, wo, cards = routed(tenant_a, method)
    shopfloor.start_card(cards[0], user=tenant_a.owner)
    shopfloor.finish_card(cards[0], user=tenant_a.owner)
    with pytest.raises(BusinessRuleError) as exc:
        shopfloor.start_card(cards[0], user=tenant_a.owner)
    assert exc.value.get_codes() == "MFG_CARD_DONE"


def test_a_card_cannot_run_on_an_order_that_is_not_running(tenant_a, method):
    company, fg, comp, cut, sew, bom, wo, cards = routed(tenant_a, method)
    WorkOrder.objects.filter(pk=wo.pk).update(status="COMPLETED")
    with pytest.raises(BusinessRuleError) as exc:
        shopfloor.start_card(cards[0], user=tenant_a.owner)
    assert exc.value.get_codes() == "MFG_BAD_WO_STATUS"


def test_finishing_adds_labour_machine_and_overhead_cost_to_the_order(tenant_a, method):
    company, fg, comp, cut, sew, bom, wo, cards = routed(tenant_a, method, costing=True)
    card = cards[0]
    shopfloor.start_card(card, user=tenant_a.owner)
    backdate_open_log(card, 90)
    done = shopfloor.finish_card(card, qty_good=100, user=tenant_a.owner)
    assert (done.labour_cost, done.machine_cost, done.overhead_cost) == (D("180.00"), D("450.00"), D("90.00"))    # 1.5 hours
    assert done.absorbed
    wo.refresh_from_db()
    assert wo.cost_absorbed == D("720.00") and wo.wip_value == D("720.00")
    assert account_net(company, "5430") == D("-180.00") and account_net(company, "5440") == D("-540.00")
    assert_all_invariants(company)
    # The cost is part of the finished goods that follow.
    wl = wo.component_lines.get()
    issue_svc.post_issue(issue_svc.create_issue(wo, tenant_a.owner, [{"wo_line": wl, "qty": 100}]), tenant_a.owner)
    rec = receipt_svc.post_receipt(receipt_svc.create_receipt(wo, tenant_a.owner, {"is_final": True}), tenant_a.owner)
    assert rec.total_cost == D("1720.00")                                  # 100 x 10 of material + 720 of conversion
    assert_all_invariants(company)


def test_cost_is_recorded_on_the_card_but_not_absorbed_without_the_flag(tenant_a, method):
    company, fg, comp, cut, sew, bom, wo, cards = routed(tenant_a, method, costing=False)
    shopfloor.start_card(cards[0], user=tenant_a.owner)
    backdate_open_log(cards[0], 60)
    done = shopfloor.finish_card(cards[0], user=tenant_a.owner)
    wo.refresh_from_db()
    assert done.labour_cost == D("120.00") and not done.absorbed and wo.cost_absorbed == 0
    assert_all_invariants(company)


def test_reopening_a_finished_card_takes_its_cost_back(tenant_a, method):
    company, fg, comp, cut, sew, bom, wo, cards = routed(tenant_a, method, costing=True)
    shopfloor.start_card(cards[0], user=tenant_a.owner)
    backdate_open_log(cards[0], 60)
    shopfloor.finish_card(cards[0], user=tenant_a.owner)
    shopfloor.reopen_card(cards[0], tenant_a.owner)
    wo.refresh_from_db()
    cards[0].refresh_from_db()
    assert cards[0].status == "PAUSED" and not cards[0].absorbed and wo.cost_absorbed == 0
    assert account_net(company, "5430") == 0 and account_net(company, "5440") == 0
    assert_all_invariants(company)


def test_a_card_whose_cost_is_in_finished_goods_cannot_be_reopened(tenant_a, method):
    company, fg, comp, cut, sew, bom, wo, cards = routed(tenant_a, method, costing=True)
    shopfloor.start_card(cards[0], user=tenant_a.owner)
    backdate_open_log(cards[0], 60)
    shopfloor.finish_card(cards[0], user=tenant_a.owner)
    wl = wo.component_lines.get()
    issue_svc.post_issue(issue_svc.create_issue(wo, tenant_a.owner, [{"wo_line": wl, "qty": 100}]), tenant_a.owner)
    receipt_svc.post_receipt(receipt_svc.create_receipt(wo, tenant_a.owner, {"is_final": False, "lines": [{"kind": "MAIN", "qty_good": 100}]}), tenant_a.owner)
    with pytest.raises(BusinessRuleError) as exc:
        shopfloor.reopen_card(cards[0], tenant_a.owner)
    assert exc.value.get_codes() == "MFG_REVERSAL_ORDER"


# --- machines, downtime, maintenance ---------------------------------------------------------------------

def test_downtime_has_one_open_stoppage_per_work_centre(tenant_a):
    prepare(tenant_a)
    floor_on(tenant_a)
    cut, sew = centres(tenant_a)
    reason = DowntimeReason.objects.create(company=tenant_a.company, code="PWR", name="Power cut")
    ev = shopfloor.start_downtime(tenant_a.company, tenant_a.owner, work_centre=cut, reason=reason)
    with pytest.raises(BusinessRuleError) as exc:
        shopfloor.start_downtime(tenant_a.company, tenant_a.owner, work_centre=cut, reason=reason)
    assert exc.value.get_codes() == "MFG_DOWNTIME_OPEN"
    shopfloor.start_downtime(tenant_a.company, tenant_a.owner, work_centre=sew, reason=reason)       # another centre is fine
    DowntimeEvent.objects.filter(pk=ev.pk).update(started_at=timezone.now() - timedelta(minutes=25))
    ended = shopfloor.end_downtime(ev)
    assert ended.minutes == D("25.00")
    with pytest.raises(BusinessRuleError):
        shopfloor.end_downtime(ev)


def test_machine_hours_drive_hour_based_maintenance(tenant_a, method):
    company, fg, comp, cut, sew, bom, wo, cards = routed(tenant_a, method)
    machine = Machine.objects.create(company=company, code="M1", name="Cutter", work_centre=cut)
    plan = MaintenancePlan.objects.create(company=company, machine=machine, name="Grease", interval_hours=1, interval_days=30)
    assert shopfloor.maintenance_due(company)[0]["overdue"] is True                       # never done: due now
    shopfloor.complete_preventive(plan, tenant_a.owner, cost=200)
    assert shopfloor.maintenance_due(company)[0]["overdue"] is False
    shopfloor.start_card(cards[0], user=tenant_a.owner)
    backdate_open_log(cards[0], 90)
    shopfloor.finish_card(cards[0], user=tenant_a.owner)
    machine.refresh_from_db()
    assert machine.run_hours == D("1.50")
    due = shopfloor.maintenance_due(company)[0]
    assert due["overdue"] is True and due["hours_left"] == D("-0.50")                       # one hour interval, 1.5 run
    shopfloor.complete_preventive(plan, tenant_a.owner)
    assert shopfloor.maintenance_due(company)[0]["overdue"] is False


def test_a_breakdown_stops_the_work_centre_until_it_is_fixed(tenant_a):
    from manufacturing.models import MaintenanceLog

    prepare(tenant_a)
    floor_on(tenant_a)
    cut, sew = centres(tenant_a)
    machine = Machine.objects.create(company=tenant_a.company, code="M2", name="Press", work_centre=cut)
    log = shopfloor.report_breakdown(tenant_a.company, tenant_a.owner, machine=machine, description="Belt snapped")
    assert DowntimeEvent.objects.filter(work_centre=cut, ended_at__isnull=True).exists()
    with pytest.raises(BusinessRuleError) as exc:
        shopfloor.report_breakdown(tenant_a.company, tenant_a.owner, machine=machine, description="again")
    assert exc.value.get_codes() == "MFG_BREAKDOWN_OPEN"
    MaintenanceLog.objects.filter(pk=log.pk).update(reported_at=timezone.now() - timedelta(minutes=70))
    done = shopfloor.resolve_breakdown(log, tenant_a.owner, cost=450, notes="New belt")
    assert done.downtime_minutes == D("70.00") and done.cost == D("450.00")
    assert not DowntimeEvent.objects.filter(work_centre=cut, ended_at__isnull=True).exists()


# --- load and utilisation ------------------------------------------------------------------------------

def test_load_is_spread_to_the_due_date_and_flags_an_overloaded_day(tenant_a, method):
    company = prepare(tenant_a, method=method)
    floor_on(tenant_a)
    cut, sew = centres(tenant_a)
    fg = make_product(company, sku="LD-FG")
    comp = stocked(tenant_a, "LD-C", 1000, 1)
    bom = make_bom(company, fg, [(comp, 1)], user=tenant_a.owner)
    shopfloor.set_routing(bom, [{"sequence": 10, "name": "Cut", "work_centre": cut, "run_minutes_per_unit": D("6")}], tenant_a.owner)
    start = timezone.localdate()
    # 100 units x 6 minutes = 600 minutes on a centre that has 480 a day: one day is too much, five days is fine.
    tight = release_work_order(make_wo(company, bom, 100, user=tenant_a.owner, planned_start=start, due_date=start), tenant_a.owner)
    shopfloor.create_job_cards(tight, tenant_a.owner)
    day = next(d for d in shopfloor.load(company, start, 3)["work_centres"] if d["code"] == "CUT")
    assert day["days"][0]["minutes"] == D("600.0") and day["days"][0]["overloaded"] is True and day["overloaded_days"] == 1


@pytest.mark.usefixtures("noon_today")
def test_utilisation_sets_hours_worked_against_hours_available(tenant_a, method):
    company, fg, comp, cut, sew, bom, wo, cards = routed(tenant_a, method)
    shopfloor.start_card(cards[0], user=tenant_a.owner)
    backdate_open_log(cards[0], 120)
    shopfloor.finish_card(cards[0], qty_good=100, user=tenant_a.owner)
    today = timezone.localdate()
    rows_ = {r["code"]: r for r in shopfloor.utilisation(company, today, today)}
    assert rows_["CUT"]["worked_minutes"] == D("120.00") and rows_["CUT"]["available_minutes"] == D(480)
    assert rows_["CUT"]["utilisation_pct"] == D("25.0") and rows_["CUT"]["good_per_hour"] == D("50.00")
    people = shopfloor.labour_productivity(company, today, today)
    assert people[0]["hours"] == D("2.00") and people[0]["cards"] == 1


# --- API ---------------------------------------------------------------------------------------------

def test_shop_floor_api_is_dark_without_the_flag(tenant_a):
    prepare(tenant_a)
    assert tenant_a.client.get("/api/v1/manufacturing/work-centres/").status_code == 404
    floor_on(tenant_a)
    assert tenant_a.client.get("/api/v1/manufacturing/work-centres/").status_code == 200


def test_shop_floor_api_setup_routing_and_cards(tenant_a):
    company = prepare(tenant_a)
    floor_on(tenant_a)
    api = tenant_a.client
    wc = api.post("/api/v1/manufacturing/work-centres/", {"code": "WLD", "name": "Welding", "labour_rate": "90"}, format="json")
    assert wc.status_code == 201, wc.data
    wc_id = body(wc)["id"]
    _i, inv = member(tenant_a, "INVENTORY_STAFF", can_manage_inventory=True)
    assert inv.post("/api/v1/manufacturing/work-centres/", {"code": "X", "name": "x"}, format="json").status_code == 403
    fg = make_product(company, sku="API-FG")
    comp = stocked(tenant_a, "API-C", 100, 5)
    bom = make_bom(company, fg, [(comp, 1)], user=tenant_a.owner)
    put = api.put(f"/api/v1/manufacturing/boms/{bom.pk}/routing/", {"operations": [
        {"sequence": 10, "name": "Weld", "work_centre": wc_id, "setup_minutes": "10", "run_minutes_per_unit": "2"},
    ]}, format="json")
    assert put.status_code == 200 and body(put)["operations"][0]["work_centre_code"] == "WLD"
    assert inv.put(f"/api/v1/manufacturing/boms/{bom.pk}/routing/", {"operations": []}, format="json").status_code == 403
    wo = release_work_order(make_wo(company, bom, 10, user=tenant_a.owner), tenant_a.owner)
    made = inv.post("/api/v1/manufacturing/job-cards/create-for-order/", {"work_order": wo.pk}, format="json")
    assert made.status_code == 201 and D(body(made)[0]["planned_minutes"]) == D("30")
    cid = body(made)[0]["id"]
    assert inv.post(f"/api/v1/manufacturing/job-cards/{cid}/start/").status_code == 200
    assert inv.post(f"/api/v1/manufacturing/job-cards/{cid}/report/", {"qty_good": 4}, format="json").status_code == 200
    fin = inv.post(f"/api/v1/manufacturing/job-cards/{cid}/finish/", {"qty_good": 6}, format="json")
    assert fin.status_code == 200 and body(fin)["status"] == "DONE" and D(body(fin)["qty_good"]) == D(10)
    assert inv.post(f"/api/v1/manufacturing/job-cards/{cid}/reopen/").status_code == 403           # reopening is a manager's
    assert api.post(f"/api/v1/manufacturing/job-cards/{cid}/reopen/").status_code == 200
    assert api.get("/api/v1/manufacturing/load/").status_code == 200
    today = timezone.localdate()
    assert api.get(f"/api/v1/manufacturing/utilisation/?from={today}&to={today}").status_code == 200
    assert api.get("/api/v1/manufacturing/utilisation/").status_code == 400


# --- tablet sign-in --------------------------------------------------------------------------------------

def tablet_world(tenant):
    company = prepare(tenant)
    floor_on(tenant)
    cut, sew = centres(tenant)
    fg = make_product(company, sku="TB-FG")
    comp = stocked(tenant, "TB-C", 100, 5)
    bom = make_bom(company, fg, [(comp, 1)], user=tenant.owner)
    shopfloor.set_routing(bom, [{"sequence": 10, "name": "Cut", "work_centre": cut, "run_minutes_per_unit": D(1)}], tenant.owner)
    wo = release_work_order(make_wo(company, bom, 10, user=tenant.owner), tenant.owner)
    cards = shopfloor.create_job_cards(wo, tenant.owner)
    op = shopfloor.create_operator(company, tenant.owner, code="OP1", name="Sita", pin="4821")
    return company, op, cards[0], APIClient()


def login(client, company, code="OP1", pin="4821"):
    return client.post("/api/v1/manufacturing/tablet/login/", {"company": company.pk, "code": code, "pin": pin}, format="json")


def test_an_operator_signs_in_with_a_pin_and_works_a_card(tenant_a):
    company, op, card, tablet = tablet_world(tenant_a)
    resp = login(tablet, company)
    assert resp.status_code == 200, resp.data
    token = body(resp)["token"]
    hdr = {"HTTP_X_OPERATOR_TOKEN": token}
    cards = tablet.get("/api/v1/manufacturing/tablet/cards/", **hdr)
    assert cards.status_code == 200 and [c["id"] for c in body(cards)["cards"]] == [card.pk]
    assert tablet.post(f"/api/v1/manufacturing/tablet/cards/{card.pk}/start/", **hdr).status_code == 200
    log = TimeLog.objects.get(job_card=card)
    assert log.operator_id == op.pk and log.user_id is None                                # the work is the operator's, not a login's
    rep = tablet.post(f"/api/v1/manufacturing/tablet/cards/{card.pk}/report/", {"qty_good": 4}, format="json", **hdr)
    assert rep.status_code == 200
    done = tablet.post(f"/api/v1/manufacturing/tablet/cards/{card.pk}/finish/", {"qty_good": 6}, format="json", **hdr)
    assert done.status_code == 200 and body(done)["status"] == "DONE"
    assert tablet.post(f"/api/v1/manufacturing/tablet/cards/{card.pk}/explode/", **hdr).status_code == 404


def test_the_tablet_needs_a_token_and_a_good_one(tenant_a):
    company, op, card, tablet = tablet_world(tenant_a)
    assert tablet.get("/api/v1/manufacturing/tablet/cards/").status_code == 403
    assert tablet.get("/api/v1/manufacturing/tablet/cards/", HTTP_X_OPERATOR_TOKEN="forged").status_code == 403
    token = body(login(tablet, company))["token"]
    Operator.objects.filter(pk=op.pk).update(is_active=False)                             # switched off: the token stops working at once
    assert tablet.get("/api/v1/manufacturing/tablet/cards/", HTTP_X_OPERATOR_TOKEN=token).status_code == 403


def test_a_token_works_only_in_its_own_company(tenant_a, tenant_b):
    company, op, card, tablet = tablet_world(tenant_a)
    token = body(login(tablet, company))["token"]
    # Another company's job card is not reachable with this token.
    prepare(tenant_b)
    floor_on(tenant_b)
    other = tablet_world_other(tenant_b)
    assert tablet.post(f"/api/v1/manufacturing/tablet/cards/{other.pk}/start/", HTTP_X_OPERATOR_TOKEN=token).status_code == 404


def tablet_world_other(tenant):
    cut, sew = centres(tenant)
    fg = make_product(tenant.company, sku="TB2-FG")
    comp = stocked(tenant, "TB2-C", 100, 5)
    bom = make_bom(tenant.company, fg, [(comp, 1)], user=tenant.owner)
    shopfloor.set_routing(bom, [{"sequence": 10, "name": "Cut", "work_centre": cut, "run_minutes_per_unit": D(1)}], tenant.owner)
    wo = release_work_order(make_wo(tenant.company, bom, 10, user=tenant.owner), tenant.owner)
    return shopfloor.create_job_cards(wo, tenant.owner)[0]


def test_five_wrong_pins_lock_the_operator_for_a_while(tenant_a):
    company, op, card, tablet = tablet_world(tenant_a)
    for _ in range(5):
        bad = login(tablet, company, pin="0000")
        assert bad.status_code == 400 and "MFG_LOGIN_FAILED" in str(bad.data)
    locked = login(tablet, company, pin="4821")                                              # even the right PIN is refused now
    assert locked.status_code == 400 and "MFG_LOGIN_LOCKED" in str(locked.data)
    Operator.objects.filter(pk=op.pk).update(locked_until=timezone.now() - timedelta(minutes=1))
    assert login(tablet, company, pin="4821").status_code == 200


def test_a_wrong_code_gives_the_same_answer_as_a_wrong_pin(tenant_a):
    company, op, card, tablet = tablet_world(tenant_a)
    a = login(tablet, company, code="NOBODY", pin="1234")
    b = login(tablet, company, pin="9999")
    assert a.status_code == b.status_code == 400 and "MFG_LOGIN_FAILED" in str(a.data) and "MFG_LOGIN_FAILED" in str(b.data)


def test_pins_are_stored_hashed_and_must_be_digits(tenant_a):
    company, op, card, tablet = tablet_world(tenant_a)
    assert "4821" not in op.pin_hash and op.pin_hash.startswith(("pbkdf2", "argon2", "bcrypt", "md5", "sha"))
    for bad in ("12", "12ab", "123456789", ""):
        with pytest.raises(BusinessRuleError):
            shopfloor.create_operator(company, tenant_a.owner, code=f"X{bad}", name="x", pin=bad)
    with pytest.raises(BusinessRuleError) as exc:
        shopfloor.create_operator(company, tenant_a.owner, code="op1", name="dup", pin="1111")
    assert exc.value.get_codes() == "MFG_OPERATOR_EXISTS"


def test_the_tablet_is_dark_when_the_company_turns_the_flag_off(tenant_a):
    company, op, card, tablet = tablet_world(tenant_a)
    token = body(login(tablet, company))["token"]
    tenant_a.company.feature_flags = {}
    tenant_a.company.save(update_fields=["feature_flags"])
    assert tablet.get("/api/v1/manufacturing/tablet/cards/", HTTP_X_OPERATOR_TOKEN=token).status_code == 404
    assert login(tablet, company).status_code == 404


def test_managers_set_up_operators_through_the_api(tenant_a):
    company = prepare(tenant_a)
    floor_on(tenant_a)
    api = tenant_a.client
    made = api.post("/api/v1/manufacturing/operators/", {"code": "OP9", "name": "Ravi", "pin": "5566"}, format="json")
    assert made.status_code == 201 and "pin" not in made.data and "pin_hash" not in made.data
    oid = body(made)["id"]
    _i, inv = member(tenant_a, "INVENTORY_STAFF", can_manage_inventory=True)
    assert inv.post("/api/v1/manufacturing/operators/", {"code": "OP8", "name": "x", "pin": "1234"}, format="json").status_code == 403
    assert api.post(f"/api/v1/manufacturing/operators/{oid}/set-pin/", {"pin": "7788"}, format="json").status_code == 200
    assert api.post(f"/api/v1/manufacturing/operators/{oid}/deactivate/").status_code == 200
    assert login(APIClient(), company, code="OP9", pin="7788").status_code == 400
    assert api.post(f"/api/v1/manufacturing/operators/{oid}/activate/").status_code == 200
    assert login(APIClient(), company, code="OP9", pin="7788").status_code == 200


# --- a tablet that lost its connection resends what happened, once ---------------------------------------

def test_a_resent_tap_keeps_the_time_it_happened_and_is_applied_once(tenant_a):
    company, op, card, tablet = tablet_world(tenant_a)
    hdr = {"HTTP_X_OPERATOR_TOKEN": body(login(tablet, company))["token"]}
    base = f"/api/v1/manufacturing/tablet/cards/{card.pk}"
    began = timezone.now() - timedelta(minutes=90)
    stopped = timezone.now() - timedelta(minutes=30)
    start = tablet.post(f"{base}/start/", {"occurred_at": began.isoformat()}, format="json", HTTP_IDEMPOTENCY_KEY="off-1", **hdr)
    again = tablet.post(f"{base}/start/", {"occurred_at": began.isoformat()}, format="json", HTTP_IDEMPOTENCY_KEY="off-1", **hdr)
    assert start.status_code == 200 and again.status_code == 200 and body(start) == body(again)
    assert TimeLog.objects.filter(job_card=card).count() == 1
    assert abs((TimeLog.objects.get(job_card=card).started_at - began).total_seconds()) < 1
    done = tablet.post(f"{base}/finish/", {"qty_good": 10, "occurred_at": stopped.isoformat()}, format="json", HTTP_IDEMPOTENCY_KEY="off-2", **hdr)
    assert done.status_code == 200 and body(done)["status"] == "DONE"
    card.refresh_from_db()
    assert card.minutes_worked == D("60.00")                                  # 90 minutes ago to 30 minutes ago
    replay = tablet.post(f"{base}/finish/", {"qty_good": 10, "occurred_at": stopped.isoformat()}, format="json", HTTP_IDEMPOTENCY_KEY="off-2", **hdr)
    assert replay.status_code == 200 and card.qty_good == D(10)               # the second finish did not add 10 more


def test_a_time_that_is_too_old_or_in_the_future_is_not_believed(tenant_a):
    company, op, card, tablet = tablet_world(tenant_a)
    hdr = {"HTTP_X_OPERATOR_TOKEN": body(login(tablet, company))["token"]}
    long_ago = timezone.now() - timedelta(days=3)
    tablet.post(f"/api/v1/manufacturing/tablet/cards/{card.pk}/start/", {"occurred_at": long_ago.isoformat()}, format="json", **hdr)
    assert (timezone.now() - TimeLog.objects.get(job_card=card).started_at).total_seconds() < 60
    assert shopfloor.when(timezone.now() + timedelta(hours=5)) <= timezone.now() + timedelta(seconds=5)
