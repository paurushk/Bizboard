"""The web sends camelCase bodies (web/src/api/mfg.ts). The server must accept exactly what the screens build."""

import json
from decimal import Decimal

import pytest
from django.utils import timezone

from manufacturing import demo
from manufacturing.models import MaterialIssue, ProductionReceipt, WorkOrder
from manufacturing.services import release_work_order
from tests.conftest import make_supplier
from tests.mfg_helpers import make_wo

pytestmark = pytest.mark.django_db

BASE = "/api/v1/manufacturing"
TODAY = timezone.localdate().isoformat()


def post(client, url, body, **extra):
    resp = client.post(url, body, format="json", **extra)
    assert resp.status_code in (200, 201), (url, resp.status_code, resp.content[:400])
    return json.loads(resp.content)["data"]


@pytest.fixture
def world(tenant_a):
    built = demo.build(tenant_a.company, tenant_a.owner)
    return tenant_a.client, tenant_a, built


def test_quick_production_accepts_the_screens_body(world):
    client, tenant, built = world
    out = post(client, f"{BASE}/quick-production/", {
        "product": built["biscuit"].pk, "qty": "10", "docDate": TODAY, "batchNo": "WEB-1",
        "expDate": "2030-01-01", "notes": "from the screen",
    }, HTTP_IDEMPOTENCY_KEY="web-q-1")
    assert out["number"].startswith("WO-") and out["status"] in ("COMPLETED", "CLOSED")
    body = {
        "product": built["biscuit"].pk, "qty": "10", "docDate": TODAY, "batchNo": "WEB-1",
        "expDate": "2030-01-01", "notes": "from the screen",
    }
    again = post(client, f"{BASE}/quick-production/", body, HTTP_IDEMPOTENCY_KEY="web-q-1")
    assert again["id"] == out["id"]                     # the same attempt key is the same order
    changed = client.post(f"{BASE}/quick-production/", {**body, "qty": "11"}, format="json", HTTP_IDEMPOTENCY_KEY="web-q-1")
    assert changed.status_code == 422                   # one key on a different body is refused: the screen must re-key on any edit
    assert WorkOrder.objects.filter(company=tenant.company).count() == 1


def test_work_order_documents_accept_the_screens_bodies(world):
    client, tenant, built = world
    company, user = tenant.company, tenant.owner
    wo = release_work_order(make_wo(company, built["biscuit_bom"], 10, user=user), user)
    line = wo.component_lines.first()
    issue = post(client, f"{BASE}/material-issues/", {
        "workOrder": wo.pk, "docDate": TODAY, "lines": [{"woLine": line.pk, "qty": str(line.qty / 2)}],
    }, HTTP_IDEMPOTENCY_KEY="web-i-1")
    assert issue["status"] == "DRAFT" and issue["lines"][0]["woLine"] == line.pk
    posted = post(client, f"{BASE}/material-issues/{issue['id']}/post/", {}, HTTP_IDEMPOTENCY_KEY="web-i-2")
    assert posted["status"] == "POSTED"
    ret = post(client, f"{BASE}/material-returns/", {
        "workOrder": wo.pk, "docDate": TODAY, "lines": [{"woLine": line.pk, "qty": "1"}],
    }, HTTP_IDEMPOTENCY_KEY="web-r-1")
    assert post(client, f"{BASE}/material-returns/{ret['id']}/post/", {}, HTTP_IDEMPOTENCY_KEY="web-r-2")["status"] == "POSTED"
    rest = post(client, f"{BASE}/material-issues/", {"workOrder": wo.pk, "docDate": TODAY}, HTTP_IDEMPOTENCY_KEY="web-i-3")
    post(client, f"{BASE}/material-issues/{rest['id']}/post/", {}, HTTP_IDEMPOTENCY_KEY="web-i-4")
    receipt = post(client, f"{BASE}/production-receipts/", {
        "workOrder": wo.pk, "docDate": TODAY, "isFinal": True, "batchNo": "WEB-2", "expDate": "2030-01-01",
        "lines": [{"kind": "MAIN", "qtyGood": "10", "qtyRejected": "0", "qtyRework": "0"}],
    }, HTTP_IDEMPOTENCY_KEY="web-p-1")
    assert receipt["isFinal"] is True
    done = post(client, f"{BASE}/production-receipts/{receipt['id']}/post/", {"overrideWip": False}, HTTP_IDEMPOTENCY_KEY="web-p-2")
    assert done["status"] == "POSTED"
    rev = post(client, f"{BASE}/production-receipts/{receipt['id']}/reverse/", {"reason": "typed wrong batch"}, HTTP_IDEMPOTENCY_KEY="web-p-3")
    assert rev["status"] == "REVERSED" and rev["reverseReason"] == "typed wrong batch"
    assert MaterialIssue.objects.filter(work_order=wo).count() == 2 and ProductionReceipt.objects.filter(work_order=wo).count() == 1


def test_recipe_save_and_routing_accept_the_screens_bodies(world):
    client, tenant, built = world
    bom = built["biscuit_bom"]
    revised = post(client, f"{BASE}/boms/{bom.pk}/revise/", {"reason": "less sugar"})
    detail = json.loads(client.get(f"{BASE}/boms/{revised['id']}/").content)["data"]
    saved = client.patch(f"{BASE}/boms/{revised['id']}/", {
        "name": "Biscuits v2", "outputQty": "10", "yieldPct": "98", "changeReason": "less sugar",
        "lines": [{"component": ln["component"], "qty": ln["qty"], "scrapPct": "1", "issueMethod": "MANUAL", "isPhantom": ln.get("isPhantom", False), "isOptional": False} for ln in detail["lines"]],
        "outputs": [{"product": built["crumbs"].pk, "kind": "BY_PRODUCT", "qty": "0.3"}],
        "additionalCosts": [{"label": "Oven labour", "element": "LABOUR", "basis": "PER_BATCH", "amount": "40"}],
    }, format="json")
    assert saved.status_code == 200, saved.content[:400]
    routed = client.put(f"{BASE}/boms/{revised['id']}/routing/", {"operations": [
        {"sequence": 10, "name": "Bake", "workCentre": built["centre"].pk, "setupMinutes": "5", "runMinutesPerUnit": "2"},
    ]}, format="json")
    assert routed.status_code == 200, routed.content[:400]
    assert post(client, f"{BASE}/boms/{revised['id']}/activate/", {"makeDefault": True})["status"] == "ACTIVE"


def test_job_work_and_quality_accept_the_screens_bodies(world):
    client, tenant, built = world
    flags = dict(tenant.company.feature_flags or {})
    flags.update({"MFG_JOB_WORK": True, "MFG_QUALITY": True})
    tenant.company.feature_flags = flags
    tenant.company.save(update_fields=["feature_flags"])
    supplier = make_supplier(tenant.company, name="Dye House")
    order = post(client, "/api/v1/jobwork/orders/", {
        "direction": "OUT", "supplier": supplier.pk, "process": "Dyeing", "directSupplyDeclared": False,
    }, HTTP_IDEMPOTENCY_KEY="web-j-1")
    ch = post(client, "/api/v1/jobwork/challans/", {
        "order": order["id"], "challanDate": TODAY, "vehicleNo": "KA01AB1234",
        "lines": [{"product": built["flour"].pk, "qty": "10", "goodsKind": "INPUT"}],
    }, HTTP_IDEMPOTENCY_KEY="web-j-2")
    assert post(client, f"/api/v1/jobwork/challans/{ch['id']}/issue/", {}, HTTP_IDEMPOTENCY_KEY="web-j-3")["status"] == "ISSUED"
    rc = post(client, "/api/v1/jobwork/receipts/", {
        "order": order["id"], "receiptDate": TODAY,
        "lines": [{"kind": "UNPROCESSED_RETURN", "product": built["flour"].pk, "qty": "4"}],
    }, HTTP_IDEMPOTENCY_KEY="web-j-4")
    assert post(client, f"/api/v1/jobwork/receipts/{rc['id']}/post/", {}, HTTP_IDEMPOTENCY_KEY="web-j-5")["status"] == "POSTED"
    tpl = post(client, "/api/v1/quality/templates/", {
        "name": "Final", "stage": "FINAL", "sampleSize": 1, "parameters": [
            {"name": "Weight", "kind": "NUMERIC", "minValue": "9", "maxValue": "11", "unit": "g", "mandatory": True},
        ],
    })
    insp = post(client, "/api/v1/quality/inspections/", {
        "product": built["biscuit"].pk, "qty": "3", "stage": "FINAL", "sourceType": "BATCH", "template": tpl["id"],
    }, HTTP_IDEMPOTENCY_KEY="web-q-9")
    result_id = str(insp["results"][0]["id"])
    post(client, f"/api/v1/quality/inspections/{insp['id']}/record-results/", {"results": {result_id: "10"}})
    done = post(client, f"/api/v1/quality/inspections/{insp['id']}/complete/", {}, HTTP_IDEMPOTENCY_KEY="web-q-10")
    assert done["status"] == "COMPLETED" and done["decision"] == "PASS"


def test_shop_floor_and_planning_accept_the_screens_bodies(world):
    client, tenant, built = world
    flags = dict(tenant.company.feature_flags or {})
    flags.update({"MFG_SHOP_FLOOR": True, "MFG_PLANNING": True})
    tenant.company.feature_flags = flags
    tenant.company.save(update_fields=["feature_flags"])
    centre = post(client, f"{BASE}/work-centres/", {
        "code": "PACK", "name": "Packing", "hoursPerDay": "8", "labourRate": "100", "machineRate": "0", "overheadRate": "10",
    })
    assert centre["code"] == "PACK"
    op = post(client, f"{BASE}/operators/", {"code": "OPX", "name": "Ravi", "pin": "1357"})
    assert op["code"] == "OPX" and "pinHash" not in op
    reason = post(client, f"{BASE}/downtime-reasons/", {"code": "JAM", "name": "Jam"})
    ev = post(client, f"{BASE}/downtime/start/", {"workCentre": centre["id"], "reason": reason["id"], "notes": "belt"})
    assert post(client, f"{BASE}/downtime/{ev['id']}/end/", {})["endedAt"]
    run = post(client, f"{BASE}/mrp-runs/run/", {"horizonDays": 14})
    assert run["number"].startswith("MRP-")
    std = post(client, f"{BASE}/standard-costs/", {
        "product": built["biscuit"].pk, "effectiveFrom": "2026-10-01", "material": "5", "labour": "1", "overhead": "1",
    })
    assert Decimal(std["unitCost"]) == Decimal("7")


def test_batch_search_finds_lots_for_every_manufacturing_role(world):
    from inventory.models import BatchLot
    from tests.mfg_helpers import member

    client, tenant, built = world
    lot = BatchLot.objects.create(company=tenant.company, product=built["biscuit"], batch_no="FIND-ME-7")
    BatchLot.objects.create(company=tenant.company, product=built["biscuit"], batch_no="OTHER-1")
    hits = json.loads(client.get(f"{BASE}/batches/", {"q": "find"}).content)["data"]["results"]
    assert [h["id"] for h in hits] == [lot.pk] and hits[0]["batchNo"] == "FIND-ME-7"
    assert hits[0]["productName"] == built["biscuit"].name
    # an auditor has no inventory rights but can read a trace, so can search for the lot
    _, auditor = member(tenant, "AUDITOR")
    assert auditor.get(f"{BASE}/batches/", {"q": "find"}).status_code == 200


def test_revaluation_approval_and_subcontract_accept_the_screens_bodies(world):
    from datetime import timedelta

    from manufacturing.models import StandardCost, WorkCentre
    from manufacturing.services import shopfloor
    from tests.conftest import make_supplier

    client, tenant, built = world
    company, user = tenant.company, tenant.owner
    flags = dict(company.feature_flags or {})
    flags.update({"MFG_COSTING_GL": True, "MFG_JOB_WORK": True, "MFG_SHOP_FLOOR": True})
    company.feature_flags = flags
    company.save(update_fields=["feature_flags"])
    StandardCost.objects.create(
        company=company, product=built["flour"], effective_from=timezone.localdate() - timedelta(days=1), material=Decimal("99"),
    )
    preview = post(client, f"{BASE}/standard-revaluations/", {"asOf": TODAY, "product": built["flour"].pk, "notes": "monthly"})
    assert preview["status"] == "DRAFT" and preview["lines"] and preview["asOf"] == TODAY
    posted = post(client, f"{BASE}/standard-revaluations/{preview['id']}/post/", {}, HTTP_IDEMPOTENCY_KEY="web-rv-1")
    assert posted["status"] == "POSTED"
    undone = post(client, f"{BASE}/standard-revaluations/{posted['id']}/reverse/", {"reason": "wrong month"}, HTTP_IDEMPOTENCY_KEY="web-rv-2")
    assert undone["status"] == "REVERSED"

    wo = release_work_order(make_wo(company, built["biscuit_bom"], 10, user=user), user)
    line = wo.component_lines.first()
    issue = post(client, f"{BASE}/material-issues/", {
        "workOrder": wo.pk, "docDate": TODAY, "lines": [{"woLine": line.pk, "qty": str(line.qty * 2), "extraReason": "spill"}],
    }, HTTP_IDEMPOTENCY_KEY="web-ap-1")
    asked = post(client, f"{BASE}/material-issues/{issue['id']}/request-approval/", {"note": "need it"})
    assert asked["approval"] == "REQUESTED"
    assert post(client, f"{BASE}/material-issues/{issue['id']}/reject/", {"note": "use leftovers"})["approval"] == "REJECTED"

    centre = WorkCentre.objects.create(company=company, code="OUT1", name="Outside", kind="OUTSIDE")
    sup = make_supplier(company, name="Shine Platers")
    from tests.conftest import make_product
    from tests.mfg_helpers import make_bom

    plated = make_product(company, sku="WEB-PLATED", name="Plated item")
    plating_bom = make_bom(company, plated, [(built["flour"], 1)], user=user)
    shopfloor.set_routing(plating_bom, [
        {"sequence": 10, "name": "Plating", "work_centre": centre, "is_subcontract": True, "subcontract_supplier": sup.pk},
    ], user)
    wo2 = release_work_order(make_wo(company, plating_bom, 10, user=user), user)
    card = shopfloor.create_job_cards(wo2, user)[0]
    defaults = json.loads(client.get(f"{BASE}/job-cards/{card.pk}/subcontract-defaults/").content)["data"]
    assert defaults["supplier"] == sup.pk and defaults["lines"]
    sent = post(client, f"{BASE}/job-cards/{card.pk}/subcontract/", {
        "supplier": sup.pk, "lines": [{"product": defaults["lines"][0]["product"], "qty": "1"}],
        "expectedReturnDate": "2030-01-01", "vehicleNo": "KA01AB1234", "notes": "plating", "issue": False,
    }, HTTP_IDEMPOTENCY_KEY="web-sc-1")
    assert sent["challan"]["status"] == "DRAFT" and sent["card"]["jobworkOrderId"] == sent["order"]["id"]


def test_the_tablet_accepts_the_time_and_key_the_offline_queue_sends(world):
    from datetime import timedelta

    from rest_framework.test import APIClient

    from manufacturing.models import TimeLog, WorkCentre
    from manufacturing.services import shopfloor

    client, tenant, built = world
    company, user = tenant.company, tenant.owner
    flags = dict(company.feature_flags or {})
    flags["MFG_SHOP_FLOOR"] = True
    company.feature_flags = flags
    company.save(update_fields=["feature_flags"])
    from tests.conftest import make_product
    from tests.mfg_helpers import make_bom

    centre = WorkCentre.objects.create(company=company, code="T1", name="Tablet bench", labour_rate=Decimal("60"))
    mixed = make_product(company, sku="WEB-MIXED", name="Mixed item")
    mix_bom = make_bom(company, mixed, [(built["flour"], 1)], user=user)
    shopfloor.set_routing(mix_bom, [{"sequence": 10, "name": "Mix", "work_centre": centre, "run_minutes_per_unit": Decimal("1")}], user)
    wo = release_work_order(make_wo(company, mix_bom, 10, user=user), user)
    card = shopfloor.create_job_cards(wo, user)[0]
    shopfloor.create_operator(company, user, code="OP9", name="Asha", pin="4821")
    tablet = APIClient()
    token = json.loads(tablet.post(f"{BASE}/tablet/login/", {"company": company.pk, "code": "OP9", "pin": "4821"}, format="json").content)["data"]["token"]
    began = timezone.now() - timedelta(minutes=45)
    # exactly the body the web client sends: snake_case keys, an ISO time, a key header
    body = {"qty_good": None, "qty_rejected": None, "occurred_at": began.isoformat()}
    for _ in range(2):
        resp = tablet.post(f"{BASE}/tablet/cards/{card.pk}/start/", body, format="json", HTTP_X_OPERATOR_TOKEN=token, HTTP_IDEMPOTENCY_KEY="q-1")
        assert resp.status_code == 200, resp.content[:300]
    assert TimeLog.objects.filter(job_card=card).count() == 1
    assert abs((TimeLog.objects.get(job_card=card).started_at - began).total_seconds()) < 1
