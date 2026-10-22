"""MFG-18 - the manufacturing paths that must hold when two people (or one double click) hit them at once.

SQLite does not enforce row locks, so these run only against PostgreSQL (CI with DATABASE_URL):
posting the same issue twice, receiving the same output twice, reversing one receipt twice, issuing the
same job-work challan twice, starting one job card twice.
"""

from __future__ import annotations

import threading
from decimal import Decimal

import pytest
from django.db import connection
from rest_framework.test import APIClient

from inventory.models import StockBalance
from inventory.services import InventoryService
from jobwork.models import JobWorkChallan
from jobwork.services import out
from manufacturing.models import JobCard, MaterialIssue, ProductionReceipt, WorkCentre
from manufacturing.services import issue as issue_svc
from manufacturing.services import receipt as receipt_svc
from manufacturing.services import release_work_order, shopfloor
from tests.conftest import make_product, make_supplier
from tests.mfg_helpers import make_bom, make_wo, prepare, stocked

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.postgres]

BASE = "/api/v1/manufacturing"
JW = "/api/v1/jobwork"


def D(v):
    return Decimal(str(v))


def _require_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row-level locking (select_for_update)")


def _race(tenant, calls):
    """Run each call(client) at the same instant on its own thread and connection."""
    barrier = threading.Barrier(len(calls), timeout=15)
    results: list = [None] * len(calls)

    def runner(index, call):
        connection.close()
        client = APIClient()
        client.force_authenticate(user=tenant.owner)
        try:
            barrier.wait()
            results[index] = call(client)
        except Exception as exc:  # pragma: no cover - reported by the assertion that follows
            results[index] = exc
        finally:
            connection.close()

    threads = [threading.Thread(target=runner, args=(i, c)) for i, c in enumerate(calls)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return results


def _codes(results):
    return sorted(getattr(r, "status_code", -1) for r in results)


def _on_hand(company, product):
    return sum((b.on_hand for b in StockBalance.objects.filter(company=company, product=product)), D(0))


def _order(tenant, raw_qty=100, qty=10):
    company = prepare(tenant)
    raw = stocked(tenant, "CC-RAW", raw_qty, 10)
    fg = make_product(company, sku="CC-FG")
    bom = make_bom(company, fg, [(raw, 2)], user=tenant.owner)
    wo = make_wo(company, bom, qty, user=tenant.owner)
    release_work_order(wo, tenant.owner)
    return company, raw, fg, wo


def test_posting_the_same_issue_twice_takes_the_stock_once(tenant_a):
    _require_postgres()
    company, raw, fg, wo = _order(tenant_a)
    doc = issue_svc.create_issue(wo, tenant_a.owner, None)
    results = _race(tenant_a, [lambda c: c.post(f"{BASE}/material-issues/{doc.pk}/post/", {}, format="json")] * 2)
    codes = _codes(results)
    assert codes.count(200) == 1, codes
    assert _on_hand(company, raw) == D(80)
    assert MaterialIssue.objects.get(pk=doc.pk).status == "POSTED"


def test_receiving_the_same_output_twice_adds_it_once(tenant_a):
    _require_postgres()
    company, raw, fg, wo = _order(tenant_a)
    issue_svc.post_issue(issue_svc.create_issue(wo, tenant_a.owner, None), tenant_a.owner)
    doc = receipt_svc.create_receipt(wo, tenant_a.owner, {"is_final": True})
    results = _race(tenant_a, [lambda c: c.post(f"{BASE}/production-receipts/{doc.pk}/post/", {}, format="json")] * 2)
    codes = _codes(results)
    assert codes.count(200) == 1, codes
    assert _on_hand(company, fg) == D(10)


def test_reversing_one_receipt_twice_takes_the_output_back_once(tenant_a):
    _require_postgres()
    company, raw, fg, wo = _order(tenant_a)
    issue_svc.post_issue(issue_svc.create_issue(wo, tenant_a.owner, None), tenant_a.owner)
    doc = receipt_svc.post_receipt(receipt_svc.create_receipt(wo, tenant_a.owner, {"is_final": True}), tenant_a.owner)
    results = _race(
        tenant_a, [lambda c: c.post(f"{BASE}/production-receipts/{doc.pk}/reverse/", {"reason": "mistake"}, format="json")] * 2,
    )
    codes = _codes(results)
    assert codes.count(200) == 1, codes
    assert _on_hand(company, fg) == D(0)
    assert ProductionReceipt.objects.get(pk=doc.pk).status == "REVERSED"


def test_issuing_the_same_challan_twice_sends_the_goods_once(tenant_a):
    _require_postgres()
    company = prepare(tenant_a)
    flags = dict(company.feature_flags or {})
    flags["MFG_JOB_WORK"] = True
    company.feature_flags = flags
    company.save(update_fields=["feature_flags"])
    raw = stocked(tenant_a, "CC-JW", 100, 10)
    order = out.create_order(company, tenant_a.owner, supplier=make_supplier(company, name="Dyer"), process="Dye")
    ch = out.create_challan(order, tenant_a.owner, [{"product": raw, "qty": 60}])
    results = _race(tenant_a, [lambda c: c.post(f"/api/v1/jobwork/challans/{ch.pk}/issue/", {}, format="json")] * 2)
    codes = _codes(results)
    assert codes.count(200) == 1, codes
    own = InventoryService.default_warehouse(company)
    assert StockBalance.objects.get(company=company, product=raw, warehouse=own).on_hand == D(40)
    assert JobWorkChallan.objects.get(pk=ch.pk).status == "ISSUED"


def test_starting_one_job_card_twice_opens_one_time_log(tenant_a):
    _require_postgres()
    company = prepare(tenant_a)
    flags = dict(company.feature_flags or {})
    flags["MFG_SHOP_FLOOR"] = True
    company.feature_flags = flags
    company.save(update_fields=["feature_flags"])
    raw = stocked(tenant_a, "CC-RAW2", 100, 10)
    fg = make_product(company, sku="CC-FG2")
    bom = make_bom(company, fg, [(raw, 2)], user=tenant_a.owner)
    wc = WorkCentre.objects.create(company=company, code="CC", name="Cut", created_by=tenant_a.owner, updated_by=tenant_a.owner)
    shopfloor.set_routing(bom, [{"work_centre": wc, "name": "Cut", "run_minutes_per_unit": "1"}], tenant_a.owner)
    wo = make_wo(company, bom, 10, user=tenant_a.owner)
    release_work_order(wo, tenant_a.owner)
    shopfloor.create_job_cards(wo, tenant_a.owner)
    card = JobCard.objects.get(work_order=wo)
    _race(tenant_a, [lambda c: c.post(f"{BASE}/job-cards/{card.pk}/start/", {}, format="json")] * 2)
    assert card.time_logs.filter(ended_at__isnull=True).count() == 1


def test_posting_the_same_revaluation_twice_re_prices_once(tenant_a):
    _require_postgres()
    from datetime import timedelta

    from django.utils import timezone

    from manufacturing.models import StandardCost, StandardRevaluation
    from manufacturing.services import revaluation

    company = prepare(tenant_a, costing_gl=True)
    fg = stocked(tenant_a, "RV-RACE", 100, 10)
    StandardCost.objects.create(
        company=company, product=fg, effective_from=timezone.localdate() - timedelta(days=1), material=D(12),
    )
    run = revaluation.preview(company, tenant_a.owner)
    results = _race(tenant_a, [
        lambda c: c.post(f"{BASE}/standard-revaluations/{run.pk}/post/", {}, format="json"),
        lambda c: c.post(f"{BASE}/standard-revaluations/{run.pk}/post/", {}, format="json"),
    ])
    assert _codes(results) == [200, 400], [getattr(r, "content", r) for r in results]
    run = StandardRevaluation.objects.get(pk=run.pk)
    assert run.status == "POSTED" and run.lines.count() == 1
    assert _on_hand(company, fg) == D(100)
    value = sum((D(r["value"]) for r in __import__("inventory.services", fromlist=["x"]).InventoryValuationService.valuation(company, product=fg)), D(0))
    assert value == D("1200.00")


# --- second pass: approvals, outside steps, the tablet, re-pricing against live stock ---------------------------------

def _extra_draft(tenant):
    company, raw, fg, wo = _order(tenant)
    line = wo.component_lines.first()
    draft = issue_svc.create_issue(wo, tenant.owner, [{"wo_line": line, "qty": 30, "extra_reason": "spill"}])
    issue_svc.request_approval(draft, tenant.owner, "need it")
    return company, raw, wo, draft


def test_approving_the_same_request_twice_posts_it_once(tenant_a):
    _require_postgres()
    company, raw, wo, draft = _extra_draft(tenant_a)
    results = _race(tenant_a, [lambda c: c.post(f"{BASE}/material-issues/{draft.pk}/approve/", {}, format="json")] * 2)
    assert _codes(results).count(200) == 1, _codes(results)
    assert _on_hand(company, raw) == D(70)                        # 30 taken once, not twice
    assert MaterialIssue.objects.get(pk=draft.pk).approval == "APPROVED"


def test_approving_and_turning_down_at_the_same_instant_leaves_one_answer(tenant_a):
    _require_postgres()
    company, raw, wo, draft = _extra_draft(tenant_a)
    results = _race(tenant_a, [
        lambda c: c.post(f"{BASE}/material-issues/{draft.pk}/approve/", {}, format="json"),
        lambda c: c.post(f"{BASE}/material-issues/{draft.pk}/reject/", {"note": "no"}, format="json"),
    ])
    assert _codes(results).count(200) == 1, _codes(results)
    doc = MaterialIssue.objects.get(pk=draft.pk)
    if doc.approval == "APPROVED":
        assert doc.status == "POSTED" and _on_hand(company, raw) == D(70)
    else:
        assert doc.approval == "REJECTED" and doc.status == "DRAFT" and _on_hand(company, raw) == D(100)


def test_sending_the_same_step_out_twice_raises_one_job_work_order(tenant_a):
    _require_postgres()
    from jobwork.models import JobWorkOrder

    company = prepare(tenant_a)
    flags = dict(company.feature_flags or {})
    flags.update({"MFG_JOB_WORK": True, "MFG_SHOP_FLOOR": True})
    company.feature_flags = flags
    company.save(update_fields=["feature_flags"])
    centre = WorkCentre.objects.create(company=company, code="RACE", name="Outside", kind="OUTSIDE")
    sup = make_supplier(company, name="Race Platers")
    raw = stocked(tenant_a, "CC-SUB", 100, 10)
    fg = make_product(company, sku="CC-SUB-FG")
    bom = make_bom(company, fg, [(raw, 1)], user=tenant_a.owner)
    shopfloor.set_routing(bom, [{"sequence": 10, "name": "Plate", "work_centre": centre, "is_subcontract": True, "subcontract_supplier": sup.pk}], tenant_a.owner)
    wo = release_work_order(make_wo(company, bom, 10, user=tenant_a.owner), tenant_a.owner)
    card = shopfloor.create_job_cards(wo, tenant_a.owner)[0]
    call = lambda c: c.post(f"{BASE}/job-cards/{card.pk}/subcontract/", {"lines": [{"product": raw.pk, "qty": "5"}], "issue": True}, format="json")  # noqa: E731
    results = _race(tenant_a, [call, call])
    assert _codes(results).count(201) == 1, _codes(results)
    assert JobWorkOrder.objects.filter(company=company, job_card_id=card.pk).count() == 1
    assert _on_hand(company, raw) == D(100)                       # moved to the job worker's godown, not out of stock
    from jobwork.models import JobWorkChallan

    assert JobWorkChallan.objects.filter(company=company, status="ISSUED").count() == 1


def _tablet_race(calls):
    """Each call(client) on its own thread and connection, with no login (the tablet has none)."""
    barrier = threading.Barrier(len(calls), timeout=15)
    results: list = [None] * len(calls)

    def runner(index, call):
        connection.close()
        try:
            barrier.wait()
            results[index] = call(APIClient())
        except Exception as exc:  # pragma: no cover
            results[index] = exc
        finally:
            connection.close()

    threads = [threading.Thread(target=runner, args=(i, c)) for i, c in enumerate(calls)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return results


def _tablet_world(tenant):
    company = prepare(tenant)
    flags = dict(company.feature_flags or {})
    flags["MFG_SHOP_FLOOR"] = True
    company.feature_flags = flags
    company.save(update_fields=["feature_flags"])
    centre = WorkCentre.objects.create(company=company, code="TB", name="Bench", labour_rate=D(60))
    raw = stocked(tenant, "CC-TB", 100, 5)
    fg = make_product(company, sku="CC-TB-FG")
    bom = make_bom(company, fg, [(raw, 1)], user=tenant.owner)
    shopfloor.set_routing(bom, [{"sequence": 10, "name": "Mix", "work_centre": centre, "run_minutes_per_unit": D(1)}], tenant.owner)
    wo = release_work_order(make_wo(company, bom, 10, user=tenant.owner), tenant.owner)
    card = shopfloor.create_job_cards(wo, tenant.owner)[0]
    op = shopfloor.create_operator(company, tenant.owner, code="RC1", name="Race", pin="4821")
    return company, card, op


def test_a_tablet_tap_resent_at_once_with_the_same_key_is_applied_once(tenant_a):
    _require_postgres()
    company, card, op = _tablet_world(tenant_a)
    token = APIClient().post(f"{BASE}/tablet/login/", {"company": company.pk, "code": "RC1", "pin": "4821"}, format="json").json()["data"]["token"]

    def tap(client):
        return client.post(
            f"{BASE}/tablet/cards/{card.pk}/start/", {"occurred_at": "2026-10-21T05:00:00+00:00"}, format="json",
            HTTP_X_OPERATOR_TOKEN=token, HTTP_IDEMPOTENCY_KEY="race-tap-1",
        )

    results = _tablet_race([tap, tap, tap])
    codes = sorted(getattr(r, "status_code", 0) for r in results)
    # one does the work; a copy that arrives while it is running is told to come back (409), never a second start
    assert codes.count(200) >= 1 and set(codes) <= {200, 409}, codes
    from manufacturing.models import TimeLog

    assert TimeLog.objects.filter(job_card=card).count() == 1
    again = tap(APIClient())                                          # the tablet's retry gets the first answer
    assert again.status_code == 200
    assert TimeLog.objects.filter(job_card=card).count() == 1


def test_many_wrong_pins_at_once_still_lock_the_operator(tenant_a):
    _require_postgres()
    from manufacturing.models import Operator

    company, card, op = _tablet_world(tenant_a)
    bad = lambda c: c.post(f"{BASE}/tablet/login/", {"company": company.pk, "code": "RC1", "pin": "0000"}, format="json")  # noqa: E731
    results = _tablet_race([bad] * 12)
    codes = [getattr(r, "status_code", 0) for r in results]
    assert set(codes) == {400}, codes
    op = Operator.objects.get(pk=op.pk)
    assert op.locked_until is not None                              # no guess was lost to a race
    good = APIClient().post(f"{BASE}/tablet/login/", {"company": company.pk, "code": "RC1", "pin": "4821"}, format="json")
    assert good.status_code == 400 and "MFG_LOGIN_LOCKED" in good.content.decode()      # even the right PIN waits


def test_re_pricing_while_stock_is_being_issued_never_loses_or_invents_stock(tenant_a):
    _require_postgres()
    from datetime import timedelta

    from django.utils import timezone

    from core.invariants import assert_all_invariants
    from inventory.services import InventoryValuationService
    from manufacturing.models import StandardCost, StandardRevaluation
    from manufacturing.services import revaluation

    company = prepare(tenant_a, costing_gl=True)
    raw = stocked(tenant_a, "CC-RV", 100, 10)
    fg = make_product(company, sku="CC-RV-FG")
    bom = make_bom(company, fg, [(raw, 1)], user=tenant_a.owner)
    wo = release_work_order(make_wo(company, bom, 60, user=tenant_a.owner), tenant_a.owner)
    StandardCost.objects.create(company=company, product=raw, effective_from=timezone.localdate() - timedelta(days=1), material=D(12))
    run = revaluation.preview(company, tenant_a.owner)
    line = wo.component_lines.first()
    draft = issue_svc.create_issue(wo, tenant_a.owner, [{"wo_line": line, "qty": 60}])
    results = _race(tenant_a, [
        lambda c: c.post(f"{BASE}/standard-revaluations/{run.pk}/post/", {}, format="json"),
        lambda c: c.post(f"{BASE}/material-issues/{draft.pk}/post/", {}, format="json"),
    ])
    assert _codes(results).count(200) >= 1, [getattr(r, "content", r) for r in results]
    on_hand = _on_hand(company, raw)
    issued = D(60) if MaterialIssue.objects.get(pk=draft.pk).status == "POSTED" else D(0)
    assert on_hand == D(100) - issued                              # the re-pricing took stock out and back: net nothing
    value = sum((D(r["value"]) for r in InventoryValuationService.valuation(company, product=raw)), D(0))
    if StandardRevaluation.objects.get(pk=run.pk).status == "POSTED":
        assert value == (on_hand * D(12)).quantize(D("0.01")) or issued > 0   # lots left after an issue keep a mixed cost
    assert_all_invariants(company)
