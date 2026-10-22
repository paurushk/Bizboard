"""Depth tests (phase 1 of the test plan): the endpoints the first pass only touched on the happy path."""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from tests.conftest import make_customer, make_product, make_supplier
from tests.mfg_helpers import member, prepare, stocked

pytestmark = pytest.mark.django_db

M = "/api/v1/manufacturing"
Q = "/api/v1/quality"
J = "/api/v1/jobwork"
TODAY = timezone.localdate()


def D(v):
    return Decimal(str(v))


def switch_on(tenant, *names):
    flags = dict(tenant.company.feature_flags or {})
    flags.update({n: True for n in names})
    tenant.company.feature_flags = flags
    tenant.company.save(update_fields=["feature_flags"])


def results(resp):
    data = json.loads(resp.content)["data"]
    return data["results"] if isinstance(data, dict) and "results" in data else data


def data_of(resp):
    return json.loads(resp.content)["data"]


# --- shop floor: set-up, maintenance, breakdowns -----------------------------------------------------------------------

def test_machines_plans_breakdowns_and_their_roles(tenant_a):
    prepare(tenant_a)
    switch_on(tenant_a, "MFG_SHOP_FLOOR")
    _u, floor = member(tenant_a, "INVENTORY_STAFF", can_manage_inventory=True)
    c = tenant_a.client
    wc = c.post(f"{M}/work-centres/", {"code": "WC1", "name": "Bench", "hoursPerDay": "8"}, format="json")
    assert wc.status_code == 201, wc.content[:200]
    # the floor reads and reports, but does not set up
    assert floor.post(f"{M}/machines/", {"code": "M1", "name": "Mixer"}, format="json").status_code == 403
    machine = c.post(f"{M}/machines/", {"code": "M1", "name": "Mixer", "workCentre": data_of(wc)["id"]}, format="json")
    assert machine.status_code == 201, machine.content[:200]
    mid = data_of(machine)["id"]
    assert c.post(f"{M}/maintenance-plans/", {"machine": mid, "name": "Grease"}, format="json").status_code == 400   # no interval
    plan = c.post(f"{M}/maintenance-plans/", {"machine": mid, "name": "Grease", "intervalDays": 30}, format="json")
    assert plan.status_code == 201
    pid = data_of(plan)["id"]
    due = data_of(c.get(f"{M}/maintenance-plans/due/"))
    assert [p["plan"] for p in due["plans"]] == [pid]
    done = floor.post(f"{M}/maintenance-plans/{pid}/complete/", {"doneOn": str(TODAY), "cost": "250", "notes": "greased"}, format="json")
    assert done.status_code == 201 and D(data_of(done)["cost"]) == D(250)
    assert data_of(c.get(f"{M}/maintenance-plans/due/"))["plans"][0]["overdue"] is False
    assert floor.post(f"{M}/maintenance-plans/{pid}/complete/", {"doneOn": "tomorrow"}, format="json").status_code == 400
    # a breakdown is reported by anyone on the floor and resolved with its cost
    bd = floor.post(f"{M}/machines/{mid}/breakdown/", {"description": "Belt snapped"}, format="json")
    assert bd.status_code == 201
    log = data_of(bd)["id"]
    assert [r["id"] for r in results(c.get(f"{M}/maintenance-log/?open=1"))] == [log]
    assert floor.post(f"{M}/machines/{mid}/breakdown/", {"description": "again"}, format="json").status_code == 400   # already open
    fixed = floor.post(f"{M}/maintenance-log/{log}/resolve/", {"cost": "90", "notes": "new belt"}, format="json")
    assert fixed.status_code == 200 and data_of(fixed)["resolvedAt"]
    assert floor.post(f"{M}/maintenance-log/{log}/resolve/", {}, format="json").status_code == 400                  # already resolved
    assert results(c.get(f"{M}/maintenance-log/?open=1")) == []


def test_load_and_utilisation_need_a_period_and_a_readable_one(tenant_a):
    prepare(tenant_a)
    switch_on(tenant_a, "MFG_SHOP_FLOOR")
    c = tenant_a.client
    assert c.get(f"{M}/load/?days=7").status_code == 200
    assert c.get(f"{M}/utilisation/").status_code == 400
    assert c.get(f"{M}/utilisation/?from={TODAY}&to={TODAY - timedelta(days=3)}").status_code in (200, 400)
    assert c.get(f"{M}/utilisation/?from={TODAY - timedelta(days=7)}&to={TODAY}").status_code == 200


def test_operators_are_managed_by_managers_and_pins_are_never_returned(tenant_a):
    prepare(tenant_a)
    switch_on(tenant_a, "MFG_SHOP_FLOOR")
    _u, floor = member(tenant_a, "INVENTORY_STAFF", can_manage_inventory=True)
    c = tenant_a.client
    assert floor.post(f"{M}/operators/", {"code": "A1", "name": "Asha", "pin": "4821"}, format="json").status_code == 403
    made = c.post(f"{M}/operators/", {"code": "A1", "name": "Asha", "pin": "4821"}, format="json")
    assert made.status_code == 201 and "pin" not in made.content.decode().lower().replace("pinhash", "")
    oid = data_of(made)["id"]
    assert c.post(f"{M}/operators/", {"code": "a1", "name": "Dup", "pin": "1234"}, format="json").status_code == 400    # same code
    assert c.post(f"{M}/operators/", {"code": "B1", "name": "Bad", "pin": "12"}, format="json").status_code == 400      # short PIN
    assert c.post(f"{M}/operators/{oid}/set-pin/", {"pin": "abcd"}, format="json").status_code == 400
    assert c.post(f"{M}/operators/{oid}/set-pin/", {"pin": "99887766"}, format="json").status_code == 200
    off = c.post(f"{M}/operators/{oid}/deactivate/", {}, format="json")
    assert data_of(off)["isActive"] is False
    assert data_of(c.post(f"{M}/operators/{oid}/activate/", {}, format="json"))["isActive"] is True


# --- quality ------------------------------------------------------------------------------------------------------------

def test_defect_codes_and_templates_are_set_up_by_managers(tenant_a):
    prepare(tenant_a)
    switch_on(tenant_a, "MFG_QUALITY")
    _u, floor = member(tenant_a, "INVENTORY_STAFF", can_manage_inventory=True)
    c = tenant_a.client
    assert floor.post(f"{Q}/defect-codes/", {"code": "CRK", "name": "Crack"}, format="json").status_code == 403
    dc = c.post(f"{Q}/defect-codes/", {"code": "CRK", "name": "Crack", "severity": "MAJOR"}, format="json")
    assert dc.status_code == 201
    prod = make_product(tenant_a.company, sku="Q-P")
    tpl = c.post(f"{Q}/templates/", {
        "name": "Final", "stage": "FINAL", "product": prod.pk, "sampleSize": 2,
        "parameters": [{"name": "Colour", "kind": "PASS_FAIL", "mandatory": True}],
    }, format="json")
    assert tpl.status_code == 201
    tid = data_of(tpl)["id"]
    assert [t["id"] for t in results(c.get(f"{Q}/templates/?product={prod.pk}&stage=FINAL"))] == [tid]
    assert results(c.get(f"{Q}/templates/?stage=INCOMING")) == []
    assert floor.delete(f"{Q}/templates/{tid}/").status_code == 403
    assert c.delete(f"{Q}/templates/{tid}/").status_code in (200, 204)


def test_a_quality_problem_is_worked_through_to_closed(tenant_a):
    prepare(tenant_a)
    switch_on(tenant_a, "MFG_QUALITY")
    _u, floor = member(tenant_a, "INVENTORY_STAFF", can_manage_inventory=True)
    prod = make_product(tenant_a.company, sku="Q-N")
    made = floor.post(f"{Q}/non-conformances/", {"product": prod.pk, "qty": "3", "description": "Cracked lids"}, format="json")
    assert made.status_code == 201, made.content[:300]
    nid, number = data_of(made)["id"], data_of(made)["number"]
    assert number.startswith("NCR") and data_of(made)["status"] == "OPEN"
    assert [r["id"] for r in results(floor.get(f"{Q}/non-conformances/?status=OPEN&product={prod.pk}"))] == [nid]
    # it moves one step at a time, and each step needs what the step before it produced
    skip = floor.post(f"{Q}/non-conformances/{nid}/advance/", {"status": "CLOSED"}, format="json")
    assert skip.status_code == 400 and "QC_NCR_ORDER" in str(skip.content)
    no_cause = floor.post(f"{Q}/non-conformances/{nid}/advance/", {"status": "ACTION"}, format="json")
    assert no_cause.status_code == 400 and "QC_NCR_NEEDS_CAUSE" in str(no_cause.content)
    step1 = floor.post(f"{Q}/non-conformances/{nid}/advance/", {"status": "ACTION", "root_cause": "Mould wear"}, format="json")
    assert step1.status_code == 200 and data_of(step1)["status"] == "ACTION"
    no_action = floor.post(f"{Q}/non-conformances/{nid}/advance/", {"status": "VERIFIED"}, format="json")
    assert no_action.status_code == 400 and "QC_NCR_NEEDS_ACTION" in str(no_action.content)
    step2 = floor.post(f"{Q}/non-conformances/{nid}/advance/", {"status": "VERIFIED", "action_taken": "Mould replaced"}, format="json")
    assert step2.status_code == 200 and data_of(step2)["status"] == "VERIFIED"
    step3 = floor.post(f"{Q}/non-conformances/{nid}/advance/", {"status": "CLOSED", "preventive_action": "Monthly check"}, format="json")
    assert step3.status_code == 200 and data_of(step3)["status"] == "CLOSED" and data_of(step3)["closedAt"]
    assert floor.delete(f"{Q}/non-conformances/{nid}/").status_code == 403
    assert tenant_a.client.delete(f"{Q}/non-conformances/{nid}/").status_code in (200, 204)


def test_a_certificate_is_only_for_a_passed_inspection_and_carries_the_results(tenant_a):
    prepare(tenant_a)
    switch_on(tenant_a, "MFG_QUALITY")
    c = tenant_a.client
    prod = make_product(tenant_a.company, sku="Q-C", name="Biscuit & Co")
    tpl = data_of(c.post(f"{Q}/templates/", {
        "name": "W", "stage": "FINAL", "sampleSize": 1,
        "parameters": [{"name": "Weight", "kind": "NUMERIC", "minValue": "9", "maxValue": "11", "unit": "g", "mandatory": True}],
    }, format="json"))
    insp = data_of(c.post(f"{Q}/inspections/", {"product": prod.pk, "qty": "2", "stage": "FINAL", "sourceType": "BATCH", "template": tpl["id"]}, format="json"))
    assert c.get(f"{Q}/inspections/{insp['id']}/certificate/").status_code == 400            # not finished
    rid = str(insp["results"][0]["id"])
    c.post(f"{Q}/inspections/{insp['id']}/record-results/", {"results": {rid: "10"}}, format="json")
    assert c.post(f"{Q}/inspections/{insp['id']}/complete/", {}, format="json").status_code == 200
    cert = c.get(f"{Q}/inspections/{insp['id']}/certificate/")
    html = cert.content.decode()
    assert cert.status_code == 200 and "Weight" in html and "10" in html
    assert "Biscuit &amp; Co" in html and "Biscuit & Co" not in html                       # text is escaped on the page
    failed = data_of(c.post(f"{Q}/inspections/", {"product": prod.pk, "qty": "2", "stage": "FINAL", "sourceType": "BATCH", "template": tpl["id"]}, format="json"))
    c.post(f"{Q}/inspections/{failed['id']}/record-results/", {"results": {str(failed['results'][0]['id']): "20"}}, format="json")
    c.post(f"{Q}/inspections/{failed['id']}/complete/", {}, format="json")
    assert c.get(f"{Q}/inspections/{failed['id']}/certificate/").status_code == 400
    assert c.get(f"{Q}/supplier-scorecard/").status_code == 200


def test_an_inspection_can_be_cancelled_while_it_is_a_draft_only(tenant_a):
    prepare(tenant_a)
    switch_on(tenant_a, "MFG_QUALITY")
    c = tenant_a.client
    prod = make_product(tenant_a.company, sku="Q-X")
    insp = data_of(c.post(f"{Q}/inspections/", {"product": prod.pk, "qty": "1", "stage": "FINAL", "sourceType": "BATCH"}, format="json"))
    assert c.post(f"{Q}/inspections/{insp['id']}/cancel/", {}, format="json").status_code == 200
    assert c.post(f"{Q}/inspections/{insp['id']}/cancel/", {}, format="json").status_code == 400
    assert c.post(f"{Q}/inspections/{insp['id']}/complete/", {}, format="json").status_code == 400
    assert results(c.get(f"{Q}/inspections/?status=CANCELLED"))[0]["id"] == insp["id"]


# --- job work through the API ----------------------------------------------------------------------------------------

def test_a_customers_material_comes_in_is_used_and_goes_back(tenant_a):
    company = prepare(tenant_a)
    switch_on(tenant_a, "MFG_JOB_WORK")
    c = tenant_a.client
    cust = make_customer(company, name="Principal Mills")
    cloth = make_product(company, sku="IN-CLOTH")
    order = c.post(f"{J}/orders/", {"direction": "IN", "customer": cust.pk, "process": "Weaving"}, format="json", HTTP_IDEMPOTENCY_KEY="in-1")
    assert order.status_code == 201, order.content[:300]
    oid = data_of(order)["id"]
    assert data_of(order)["number"].startswith("JWI")
    recv = c.post(f"{J}/orders/{oid}/receive-material/", {"lines": [{"product": cloth.pk, "qty": "30"}], "vehicleNo": "KA01"}, format="json", HTTP_IDEMPOTENCY_KEY="in-2")
    assert recv.status_code == 201, recv.content[:300]
    loss = c.post(f"{J}/orders/{oid}/record-loss/", {"product": cloth.pk, "qty": "2", "reference": "wastage"}, format="json")
    assert loss.status_code == 201
    back = c.post(f"{J}/orders/{oid}/return-material/", {"lines": [{"product": cloth.pk, "qty": "28"}]}, format="json", HTTP_IDEMPOTENCY_KEY="in-3")
    assert back.status_code == 201
    over = c.post(f"{J}/orders/{oid}/return-material/", {"lines": [{"product": cloth.pk, "qty": "5"}]}, format="json", HTTP_IDEMPOTENCY_KEY="in-4")
    assert over.status_code == 400                                                        # more than is in our hands
    moves = results(c.get(f"{J}/principal-movements/?principal={cust.pk}"))
    assert sorted(m["kind"] for m in moves) == ["LOSS", "RECEIVED", "RETURNED"]
    assert [m["kind"] for m in results(c.get(f"{J}/principal-movements/?kind=LOSS"))] == ["LOSS"]
    bal = data_of(c.get(f"{J}/balance/"))
    assert bal["customersMaterial"] == [] or all(D(r["qty"]) == 0 for r in bal["customersMaterial"])
    assert [o["id"] for o in results(c.get(f"{J}/orders/?direction=IN&customer={cust.pk}"))] == [oid]
    assert c.post(f"{J}/orders/{oid}/close/", {}, format="json").status_code == 200
    assert c.post(f"{J}/orders/{oid}/receive-material/", {"lines": [{"product": cloth.pk, "qty": "1"}]}, format="json", HTTP_IDEMPOTENCY_KEY="in-5").status_code == 400


def test_out_documents_can_be_reversed_through_the_api_by_managers_only(tenant_a):
    company = prepare(tenant_a)
    switch_on(tenant_a, "MFG_JOB_WORK")
    c = tenant_a.client
    _u, floor = member(tenant_a, "INVENTORY_STAFF", can_manage_inventory=True)
    raw = stocked(tenant_a, "OUT-RAW", 100, 10)
    fin = make_product(company, sku="OUT-FIN")
    sup = make_supplier(company, name="Rev Worker")
    oid = data_of(c.post(f"{J}/orders/", {"direction": "OUT", "supplier": sup.pk, "process": "Dye"}, format="json", HTTP_IDEMPOTENCY_KEY="o-1"))["id"]
    ch = data_of(c.post(f"{J}/challans/", {"order": oid, "lines": [{"product": raw.pk, "qty": "10", "goodsKind": "INPUT"}]}, format="json", HTTP_IDEMPOTENCY_KEY="o-2"))
    assert c.post(f"{J}/challans/{ch['id']}/issue/", {}, format="json", HTTP_IDEMPOTENCY_KEY="o-3").status_code == 200
    rc = data_of(c.post(f"{J}/receipts/", {"order": oid, "lines": [{"kind": "PROCESSED", "product": fin.pk, "qty": "10", "inputProduct": raw.pk, "inputQty": "10"}]}, format="json", HTTP_IDEMPOTENCY_KEY="o-4"))
    assert c.post(f"{J}/receipts/{rc['id']}/post/", {}, format="json", HTTP_IDEMPOTENCY_KEY="o-5").status_code == 200
    assert floor.post(f"{J}/receipts/{rc['id']}/reverse/", {"reason": "x"}, format="json").status_code == 403
    assert c.post(f"{J}/receipts/{rc['id']}/reverse/", {}, format="json").status_code == 400                         # a reason is needed
    assert c.post(f"{J}/receipts/{rc['id']}/reverse/", {"reason": "counted wrong"}, format="json").status_code == 200
    assert floor.post(f"{J}/challans/{ch['id']}/reverse/", {"reason": "x"}, format="json").status_code == 403
    assert c.post(f"{J}/challans/{ch['id']}/reverse/", {"reason": "wrong party"}, format="json").status_code == 200
    assert floor.post(f"{J}/orders/{oid}/close/", {}, format="json").status_code == 403
    assert c.post(f"{J}/orders/{oid}/close/", {}, format="json").status_code == 200
    assert [r["id"] for r in results(c.get(f"{J}/challans/?order={oid}&status=REVERSED"))] == [ch["id"]]
    assert [r["id"] for r in results(c.get(f"{J}/receipts/?order={oid}"))] == [rc["id"]]


def test_ageing_balance_and_itc04_through_the_api(tenant_a):
    company = prepare(tenant_a)
    switch_on(tenant_a, "MFG_JOB_WORK")
    c = tenant_a.client
    _u, acc = member(tenant_a, "ACCOUNTANT")
    _v, floor = member(tenant_a, "INVENTORY_STAFF", can_manage_inventory=True)
    raw = stocked(tenant_a, "AG-RAW", 100, 10)
    sup = make_supplier(company, name="Age Worker")
    oid = data_of(c.post(f"{J}/orders/", {"direction": "OUT", "supplier": sup.pk}, format="json", HTTP_IDEMPOTENCY_KEY="a-1"))["id"]
    ch = data_of(c.post(f"{J}/challans/", {"order": oid, "lines": [{"product": raw.pk, "qty": "10"}]}, format="json", HTTP_IDEMPOTENCY_KEY="a-2"))
    c.post(f"{J}/challans/{ch['id']}/issue/", {}, format="json", HTTP_IDEMPOTENCY_KEY="a-3")
    ageing = data_of(c.get(f"{J}/ageing/?as_of={TODAY + timedelta(days=400)}"))
    assert ageing["overdue"] == 1 and ageing["rows"][0]["status"] == "OVERDUE"
    assert data_of(c.get(f"{J}/ageing/"))["overdue"] == 0
    assert c.get(f"{J}/ageing/?as_of=soon").status_code == 400
    held = data_of(c.get(f"{J}/balance/"))["atJobWorkers"]
    assert held[0]["supplierName"] == "Age Worker" and D(held[0]["qty"]) == 10
    frm, to = TODAY - timedelta(days=30), TODAY
    tables = data_of(c.get(f"{J}/itc04/?from={frm}&to={to}"))
    assert len(tables["table4"]) == 1
    csv_resp = c.get(f"{J}/itc04/?from={frm}&to={to}&export=csv")
    assert csv_resp.status_code == 200 and csv_resp["Content-Type"].startswith("text/csv") and "Table 4" in csv_resp.content.decode()
    assert c.get(f"{J}/itc04/").status_code == 400
    due = data_of(c.get(f"{J}/itc04-filings/due/"))
    assert due["periods"] and "label" in due["periods"][0]
    fy = TODAY.year if TODAY.month >= 4 else TODAY.year - 1
    assert floor.post(f"{J}/itc04-filings/prepare/", {"fy": fy, "half": 1}, format="json").status_code == 403
    assert acc.post(f"{J}/itc04-filings/prepare/", {"fy": "x"}, format="json").status_code == 400
    filing = acc.post(f"{J}/itc04-filings/prepare/", {"fy": fy, "half": 1}, format="json")
    assert filing.status_code == 201, filing.content[:300]
    fid = data_of(filing)["id"]
    filed = acc.post(f"{J}/itc04-filings/{fid}/mark-filed/", {"acknowledgement": "ARN123"}, format="json")
    assert filed.status_code == 200 and data_of(filed)["status"] == "FILED" and data_of(filed)["acknowledgement"] == "ARN123"
    assert acc.post(f"{J}/itc04-filings/{fid}/mark-filed/", {"filedOn": "never"}, format="json").status_code == 400
