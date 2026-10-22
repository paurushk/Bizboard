"""Faults found by the code review of the manufacturing work: unreadable input answered 500, spreadsheet formulas in
exports, a re-pricing raising a "large stock adjustment" alert, and labels for a receipt that is not posted."""

import csv
import io
import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.utils import timezone

from insights.attention import build_attention_rows
from manufacturing import demo
from manufacturing.models import StandardCost
from manufacturing.services import issue as issue_svc
from manufacturing.services import receipt as receipt_svc
from manufacturing.services import release_work_order, revaluation
from tests.conftest import make_product
from tests.mfg_helpers import make_bom, make_wo, prepare, stocked

pytestmark = pytest.mark.django_db

BASE = "/api/v1/manufacturing"


@pytest.fixture
def world(tenant_a):
    built = demo.build(tenant_a.company, tenant_a.owner)
    flags = dict(tenant_a.company.feature_flags or {})
    flags.update({"MFG_QUALITY": True, "MFG_SHOP_FLOOR": True, "MFG_JOB_WORK": True, "MFG_PLANNING": True, "MFG_COSTING_GL": True})
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    return tenant_a, built


@pytest.mark.parametrize("url", [
    "/work-orders/?product=abc",
    "/work-orders/?due_before=not-a-date",
    "/boms/?product=abc",
    "/material-issues/?work_order=abc",
    "/atp/?product=abc",
    "/load/?days=many",
    "/load/?from=yesterday",
    "/utilisation/?from=x&to=y",
    "/reports/wip/?as_of=bad",
    "/reports/variance/?from=1&to=2",
    "/batches/?product=abc",
])
def test_unreadable_filters_are_a_400_not_a_500(world, url):
    tenant, _ = world
    resp = tenant.client.get(f"{BASE}{url}")
    assert resp.status_code in (400, 404), (url, resp.status_code, resp.content[:200])
    assert resp.status_code != 500


def test_unreadable_numbers_in_a_body_are_a_400(world):
    tenant, built = world
    from manufacturing.services import shopfloor

    resp = tenant.client.post(f"{BASE}/quick-production/", {"product": built["biscuit"].pk, "qty": "abc"}, format="json")
    assert resp.status_code == 400
    assert tenant.client.post(f"{BASE}/mrp-runs/run/", {"horizon_days": "soon"}, format="json").status_code == 400
    assert tenant.client.get("/api/v1/quality/scorecard/?from=nonsense").status_code in (400, 404)
    assert shopfloor  # the tablet bodies are covered in the shop-floor tests


def test_a_text_result_for_a_numeric_check_is_a_400(world):
    tenant, built = world
    tpl = tenant.client.post("/api/v1/quality/templates/", {
        "name": "Weight", "stage": "FINAL", "sampleSize": 1,
        "parameters": [{"name": "Weight", "kind": "NUMERIC", "minValue": "9", "maxValue": "11", "unit": "g", "mandatory": True}],
    }, format="json")
    assert tpl.status_code == 201, tpl.content[:300]
    insp = tenant.client.post("/api/v1/quality/inspections/", {
        "product": built["biscuit"].pk, "qty": "1", "stage": "FINAL", "sourceType": "BATCH",
        "template": json.loads(tpl.content)["data"]["id"],
    }, format="json")
    data = json.loads(insp.content)["data"]
    result_id = str(data["results"][0]["id"])
    bad = tenant.client.post(f"/api/v1/quality/inspections/{data['id']}/record-results/", {"results": {result_id: "heavy"}}, format="json")
    assert bad.status_code == 400, bad.content[:300]


def test_exports_neutralise_spreadsheet_formulas(tenant_a):
    company = prepare(tenant_a, separate=True)
    fg = make_product(company, sku="CSV-FG", name="=HYPERLINK(\"http://evil.example\",\"click\")")
    raw = stocked(tenant_a, "CSV-RAW", 100, 10)
    bom = make_bom(company, fg, [(raw, 1)], user=tenant_a.owner)
    make_wo(company, bom, 5, user=tenant_a.owner, batch_no="@SUM(1+1)")
    resp = tenant_a.client.get(f"{BASE}/work-orders/export/")
    assert resp.status_code == 200
    rows = list(csv.reader(io.StringIO(resp.content.decode())))
    cells = [c for r in rows[1:] for c in r]
    assert "'=HYPERLINK(\"http://evil.example\",\"click\")" in cells and "'@SUM(1+1)" in cells
    assert not any(c.startswith(("=", "@", "+")) for c in cells)


def test_a_re_pricing_is_not_reported_as_a_large_stock_adjustment(tenant_a):
    company = prepare(tenant_a, costing_gl=True)
    fg = stocked(tenant_a, "RVA-FG", 500, 100)                      # 500 units, ₹50,000: well past the alert thresholds
    StandardCost.objects.create(company=company, product=fg, effective_from=timezone.localdate() - timedelta(days=1), material=Decimal("120"))
    revaluation.post(revaluation.preview(company, tenant_a.owner), tenant_a.owner)
    cache.clear()
    assert "ABNORMAL_STOCK_ADJUSTMENT" not in [r["code"] for r in build_attention_rows(company, None)]


def test_only_a_posted_receipt_prints_batch_labels(tenant_a):
    company = prepare(tenant_a, separate=True)
    fg = make_product(company, sku="LBL-FG", track_batch=True)
    raw = stocked(tenant_a, "LBL-RAW", 100, 10)
    bom = make_bom(company, fg, [(raw, 1)], user=tenant_a.owner)
    wo = release_work_order(make_wo(company, bom, 5, user=tenant_a.owner), tenant_a.owner)
    issue_svc.post_issue(issue_svc.create_issue(wo, tenant_a.owner), tenant_a.owner)
    draft = receipt_svc.create_receipt(wo, tenant_a.owner, {"batch_no": "LBL-1", "lines": [{"kind": "MAIN", "qty_good": 5}]})
    assert tenant_a.client.get(f"{BASE}/production-receipts/{draft.pk}/print-label/").status_code == 400
    posted = receipt_svc.post_receipt(draft, tenant_a.owner)
    assert tenant_a.client.get(f"{BASE}/production-receipts/{posted.pk}/print-label/").status_code == 200


def test_job_work_refuses_negative_amounts_and_goods_worth_less_than_nothing(tenant_a):
    from core.exceptions import BusinessRuleError
    from jobwork.services import out
    from tests.conftest import make_supplier

    company = prepare(tenant_a)
    raw = stocked(tenant_a, "RV-RAW", 100, 10)
    fin = make_product(company, sku="RV-FIN")
    scrap = make_product(company, sku="RV-SCRAP")
    order = out.create_order(company, tenant_a.owner, supplier=make_supplier(company, name="Rv Worker"))
    out.issue_challan(out.create_challan(order, tenant_a.owner, [{"product": raw, "qty": 10}]), tenant_a.owner)
    with pytest.raises(BusinessRuleError) as exc:
        out.create_receipt(order, tenant_a.owner, [
            {"kind": "PROCESSED", "product": fin, "qty": 10, "input_product": raw, "input_qty": 10, "charge_amount": -500},
        ])
    assert exc.value.get_codes() == "JW_BAD_QTY"
    rc = out.create_receipt(order, tenant_a.owner, [
        {"kind": "PROCESSED", "product": fin, "qty": 10, "input_product": raw, "input_qty": 10},
        {"kind": "SCRAP_RETURNED", "product": scrap, "qty": 10, "unit_cost": 50},          # 500 of scrap from 100 of material
    ])
    with pytest.raises(BusinessRuleError) as exc:
        out.post_receipt(rc, tenant_a.owner)
    assert exc.value.get_codes() == "JW_NEGATIVE_VALUE"


def test_a_failed_lot_accepts_nothing_and_a_result_must_be_a_finite_number(tenant_a):
    from core.exceptions import BusinessRuleError
    from quality import services as qc

    company = prepare(tenant_a)
    product = make_product(company, sku="QF-1")
    tpl = qc.InspectionTemplate.objects.create(company=company, name="W", stage="FINAL", sample_size=1)
    qc.InspectionParameter.objects.create(company=company, template=tpl, name="Weight", kind="NUMERIC", min_value=9, max_value=11, mandatory=True)
    insp = qc.create_inspection(company, tenant_a.owner, product=product, qty=10, source_type="INTERNAL", stage="FINAL", template=tpl)
    result_id = insp.results.get().pk
    for junk in ("NaN", "Infinity", "-Infinity"):
        with pytest.raises(BusinessRuleError) as exc:
            qc.record_results(insp, tenant_a.owner, {str(result_id): junk})
        assert exc.value.get_codes() == "QC_BAD_RESULT"
    qc.record_results(insp, tenant_a.owner, {str(result_id): "12"})                      # outside 9 to 11
    done = qc.complete_inspection(insp, tenant_a.owner, decision="FAIL", qty_accepted=Decimal("4"))
    assert (done.qty_accepted, done.qty_rejected) == (Decimal("0"), Decimal("10"))


def test_a_wrong_pin_is_counted_even_though_the_attempt_is_refused(tenant_a):
    from manufacturing.models import Operator
    from manufacturing.services import shopfloor

    company = prepare(tenant_a)
    shopfloor.create_operator(company, tenant_a.owner, code="PIN1", name="Asha", pin="4821")
    for expected in (1, 2):
        with pytest.raises(Exception):
            shopfloor.operator_login(company.pk, "PIN1", "0000")
        assert Operator.objects.get(company=company, code="PIN1").failed_attempts == expected
    shopfloor.operator_login(company.pk, "PIN1", "4821")
    assert Operator.objects.get(company=company, code="PIN1").failed_attempts == 0
    with pytest.raises(Exception):
        shopfloor.operator_login(company.pk, "NOBODY", "4821")                           # an unknown code is refused the same way
