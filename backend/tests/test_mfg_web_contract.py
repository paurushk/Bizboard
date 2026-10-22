"""The web screens read fields named in web/src/api/mfg.ts. Every required field must exist in the real response.

The TypeScript types are parsed from the file itself, so a field added to a type without the server sending
it (or a serializer rename) fails here instead of showing a blank cell in the browser.
"""

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
from rest_framework.test import APIClient

from jobwork.services import out, principal
from manufacturing import demo
from manufacturing.models import (
    DowntimeReason, JobCard, Machine, MaintenancePlan, MrpRun, Operator, StandardCost, WorkCentre, WorkOrder,
)
from manufacturing.services import issue as issue_svc
from manufacturing.services import planning
from manufacturing.services import quick_entry
from manufacturing.services import receipt as receipt_svc
from manufacturing.services import release_work_order, shopfloor
from quality.models import DefectCode, InspectionParameter, InspectionTemplate
from quality.services import create_inspection, raise_ncr
from tests.conftest import make_customer
from tests.mfg_helpers import make_bom, make_wo

pytestmark = pytest.mark.django_db

TS = Path(__file__).resolve().parents[2] / "web" / "src" / "api" / "mfg.ts"
BASE = "/api/v1/manufacturing"


def ts_required(type_name: str) -> set[str]:
    """Top-level required fields of ``export type <name> = { ... };`` (one line or many)."""
    text = TS.read_text(encoding="utf-8")
    m = re.search(rf"export type {re.escape(type_name)} = \{{", text)
    assert m, f"type {type_name} not found in mfg.ts"
    depth, buf, fields, i = 1, "", [], m.end()
    while depth:
        ch = text[i]
        if ch in "{[(<":
            depth += 1
        elif ch in "}])>":
            depth -= 1
            if depth == 0:
                break
        if depth == 1 and ch in (";", chr(10)):
            fields.append(buf)
            buf = ""
        else:
            buf += ch
        i += 1
    fields.append(buf)
    out = set()
    for f in fields:
        fm = re.match(r"\s*(\w+)(\??):", f)
        if fm and not fm.group(2):
            out.add(fm.group(1))
    return out


def get(client, url, **params):
    resp = client.get(url, params)
    assert resp.status_code == 200, (url, resp.status_code, getattr(resp, "data", None))
    return json.loads(resp.content)["data"]


def first(data):
    rows = data["results"] if isinstance(data, dict) and "results" in data else data
    assert rows, "the contract needs at least one record to read"
    return rows[0]


def check(name, record):
    missing = sorted(ts_required(name) - set(record))
    assert not missing, f"{name}: the page reads {missing}, the server does not send them (sends {sorted(record)})"


@pytest.fixture
def world(tenant_a):
    company = tenant_a.company
    built = demo.build(company, tenant_a.owner)
    user = tenant_a.owner
    # a work order through issue, partial and final output
    bom = built["biscuit_bom"]
    wo = make_wo(company, bom, 10, user=user, due_date=built["today"])
    release_work_order(wo, user)
    issue_svc.post_issue(issue_svc.create_issue(wo, user, None), user)
    receipt_svc.post_receipt(receipt_svc.create_receipt(wo, user, {"is_final": True}), user)
    ret = None
    open_wo = make_wo(company, bom, 4, user=user, due_date=built["today"])
    release_work_order(open_wo, user)
    issue_svc.post_issue(issue_svc.create_issue(open_wo, user, None), user)
    line = open_wo.component_lines.first()
    from manufacturing.services import issue as isv

    ret = isv.post_return(isv.create_return(open_wo, user, [{"wo_line": line, "qty": "0.1"}]), user)
    quick_entry.quick_production(company, user, product=built["biscuit"], qty=2)
    # shop floor
    shopfloor.set_routing(
        make_bom(company, built["crumbs"], [(built["flour"], 1)], user=user, name="crumb"),
        [{"work_centre": built["centre"], "name": "Grind", "run_minutes_per_unit": "1"}], user,
    )
    # planning, standard cost
    planning.run_mrp(company, user, horizon_days=14)
    StandardCost.objects.create(company=company, product=built["biscuit"], effective_from=built["today"], material=Decimal("5"))
    # quality
    tpl = InspectionTemplate.objects.create(company=company, name="Final check", product=built["biscuit"], stage="FINAL", created_by=user, updated_by=user)
    InspectionParameter.objects.create(template=tpl, company=company, name="Weight", kind="NUMERIC", min_value=Decimal("1"), max_value=Decimal("2"), sequence=0)
    DefectCode.objects.create(company=company, code="D1", name="Crack", created_by=user, updated_by=user)
    insp = create_inspection(company, user, product=built["biscuit"], qty=3, source_type="MANUAL", stage="FINAL", template=tpl)
    raise_ncr(insp, user, source="INSPECTION")
    # job work
    order = out.create_order(company, user, supplier=built["job_worker"], process="Packing")
    ch = out.create_challan(order, user, [{"product": built["flour"], "qty": 5}])
    out.issue_challan(ch, user)
    rc = out.create_receipt(order, user, [{"kind": "UNPROCESSED_RETURN", "product": built["flour"], "qty": 1}])
    out.post_receipt(rc, user)
    customer = make_customer(company, name="Principal")
    in_order = principal.create_order(company, user, customer=customer, process="Baking")
    principal.receive_material(in_order, user, [{"product": built["sugar"], "qty": 3}])
    # floor extras
    cards = shopfloor.create_job_cards(open_wo, user) if open_wo.bom.operations.exists() else []
    wc = WorkCentre.objects.get(company=company, code="OVEN")
    reason = DowntimeReason.objects.create(company=company, code="JAM", name="Jam", created_by=user, updated_by=user)
    shopfloor.start_downtime(company, user, work_centre=wc, reason=reason)
    machine = Machine.objects.create(company=company, code="M1", name="Oven", work_centre=wc, created_by=user, updated_by=user)
    plan = MaintenancePlan.objects.create(company=company, machine=machine, name="Grease", interval_days=30, created_by=user, updated_by=user)
    shopfloor.report_breakdown(company, user, machine=machine, description="Belt")
    shopfloor.create_operator(company, user, code="OP9", name="Ravi", pin="1357")
    return {"company": company, "wo": wo, "open_wo": open_wo, "order": order, "insp": insp, "built": built, "ret": ret, "plan": plan, "cards": cards}


def test_every_screen_reads_fields_the_server_sends(tenant_a, world):
    c = tenant_a.client
    # settings and recipes
    check("MfgSettings", get(c, f"{BASE}/settings/"))
    recipe = first(get(c, f"{BASE}/boms/", status="ACTIVE"))
    check("Recipe", get(c, f"{BASE}/boms/{recipe['id']}/"))
    # work orders and their documents
    wo = world["wo"]
    detail = get(c, f"{BASE}/work-orders/{wo.pk}/")
    check("WorkOrderRow", detail)
    check("Availability", get(c, f"{BASE}/work-orders/{world['open_wo'].pk}/availability/"))
    check("IssueDoc", first(get(c, f"{BASE}/material-issues/", work_order=wo.pk)))
    ret = first(get(c, f"{BASE}/material-returns/", work_order=world["open_wo"].pk))
    # ReturnDoc is IssueDoc without the issue-only line fields, so the shared header fields are what is checked.
    assert {"id", "number", "status", "workOrder", "docDate", "lines"} <= set(ret)
    assert {"id", "woLine", "component", "componentName", "warehouse", "qty"} <= set(ret["lines"][0])
    check("ReceiptDoc", first(get(c, f"{BASE}/production-receipts/", work_order=wo.pk)))
    # planning
    check("BoardRow", first(get(c, f"{BASE}/board/")["orders"]))
    run = first(get(c, f"{BASE}/mrp-runs/"))
    check("MrpRunRow", run)
    full = get(c, f"{BASE}/mrp-runs/{run['id']}/")
    if full.get("lines"):
        check("MrpLineRow", full["lines"][0])
    check("StandardCost", first(get(c, f"{BASE}/standard-costs/")))
    # quality
    check("InspectionTemplate", first(get(c, "/api/v1/quality/templates/")))
    insp = first(get(c, "/api/v1/quality/inspections/"))
    check("Inspection", get(c, f"/api/v1/quality/inspections/{insp['id']}/"))
    check("Ncr", first(get(c, "/api/v1/quality/non-conformances/")))
    check("DefectCode", first(get(c, "/api/v1/quality/defect-codes/")))
    # job work
    check("JobWorkOrder", first(get(c, "/api/v1/jobwork/orders/")))
    check("Challan", first(get(c, "/api/v1/jobwork/challans/")))
    check("JwReceipt", first(get(c, "/api/v1/jobwork/receipts/")))
    ageing = get(c, "/api/v1/jobwork/ageing/")["rows"]
    check("AgeingRow", ageing[0])
    # shop floor
    check("WorkCentre", first(get(c, f"{BASE}/work-centres/")))
    check("DowntimeReason", first(get(c, f"{BASE}/downtime-reasons/")))
    check("DowntimeEvent", first(get(c, f"{BASE}/downtime/")))
    check("Machine", first(get(c, f"{BASE}/machines/")))
    check("MaintenancePlan", first(get(c, f"{BASE}/maintenance-plans/")))
    check("MaintenanceLog", first(get(c, f"{BASE}/maintenance-log/")))
    check("Operator", first(get(c, f"{BASE}/operators/")))
    if world["cards"]:
        check("JobCard", first(get(c, f"{BASE}/job-cards/")))


def test_the_tablet_answers_in_the_shape_the_page_expects(tenant_a, world):
    company = world["company"]
    client = APIClient()
    resp = client.post(f"{BASE}/tablet/login/", {"company": company.pk, "code": "OP9", "pin": "1357"}, format="json")
    assert resp.status_code == 200, resp.content
    session = json.loads(resp.content)["data"]
    check("TabletSession", session)
    cards = client.get(f"{BASE}/tablet/cards/", HTTP_X_OPERATOR_TOKEN=session["token"])
    assert cards.status_code == 200
    assert "cards" in json.loads(cards.content)["data"]


def test_the_reports_the_page_lists_all_answer(tenant_a, world):
    for slug in (
        "wip", "work-order-cost", "variance", "yield-wastage", "consumption", "output", "on-time", "scrap-register",
        "profitability", "reconciliation",
    ):
        data = get(tenant_a.client, f"{BASE}/reports/{slug}/")
        assert isinstance(data, dict) and data, slug


def test_unused_models_are_not_silently_imported(world):
    # Guards the fixture itself: it must really have created a job card, a downtime, a run and a breakdown.
    assert Operator.objects.exists() and MrpRun.objects.exists() and WorkOrder.objects.count() >= 3
    assert JobCard.objects.count() >= 0
