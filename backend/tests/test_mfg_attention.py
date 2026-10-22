"""Manufacturing rows on the Needs attention feed (MFG-X2)."""

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from insights.attention import KNOWN_CODES, build_attention_rows
from manufacturing.attention import CODES
from manufacturing.services import release_work_order
from tests.conftest import make_product
from tests.mfg_helpers import make_bom, make_wo, prepare, stocked

pytestmark = pytest.mark.django_db


def codes(company, as_of=None):
    cache.clear()
    return [r["code"] for r in build_attention_rows(company, None, as_of=as_of)]


def enable(tenant, *names):
    flags = dict(tenant.company.feature_flags or {})
    flags.update({n: True for n in names})
    tenant.company.feature_flags = flags
    tenant.company.save(update_fields=["feature_flags"])


def late_order(tenant, days_late=3):
    company = prepare(tenant)
    raw = stocked(tenant, "ATT-RAW", 100, 5)
    fg = make_product(company, sku="ATT-FG")
    bom = make_bom(company, fg, [(raw, 2)], user=tenant.owner)
    wo = make_wo(company, bom, 10, user=tenant.owner, due_date=timezone.localdate() - timedelta(days=days_late))
    release_work_order(wo, tenant.owner)
    return company, wo


def test_every_manufacturing_code_is_known_to_the_feed():
    assert CODES <= KNOWN_CODES


def test_a_late_work_order_raises_a_row_that_links_to_it(tenant_a):
    company, wo = late_order(tenant_a)
    cache.clear()
    rows = [r for r in build_attention_rows(company, None) if r["code"] == "WO_LATE"]
    assert len(rows) == 1
    row = rows[0]
    assert row["dedupe_key"] == f"WO_LATE:{wo.pk}"
    assert row["action_href"] == f"/manufacturing/work-orders/{wo.pk}"
    assert row["severity"] == "warning" and row["params"]["days"] == 3


def test_a_week_late_is_critical(tenant_a):
    company, _ = late_order(tenant_a, days_late=9)
    cache.clear()
    row = next(r for r in build_attention_rows(company, None) if r["code"] == "WO_LATE")
    assert row["severity"] == "critical"


def test_nothing_appears_when_manufacturing_is_off(tenant_a):
    company, _ = late_order(tenant_a)
    flags = dict(company.feature_flags or {})
    flags["ENABLE_MANUFACTURING"] = False
    company.feature_flags = flags
    company.save(update_fields=["feature_flags"])
    assert not set(codes(company)) & CODES


def test_a_finished_order_is_not_late(tenant_a):
    from manufacturing.models import WorkOrder

    company, wo = late_order(tenant_a)
    WorkOrder.objects.filter(pk=wo.pk).update(status="CLOSED")
    assert "WO_LATE" not in codes(company)


def test_a_shortage_row_needs_the_planning_switch(tenant_a):
    company = prepare(tenant_a)
    raw = stocked(tenant_a, "SH-RAW", 1, 5)
    fg = make_product(company, sku="SH-FG")
    bom = make_bom(company, fg, [(raw, 50)], user=tenant_a.owner)
    wo = make_wo(company, bom, 1, user=tenant_a.owner, due_date=timezone.localdate() + timedelta(days=5))
    wo.status = "RELEASED"
    wo.save(update_fields=["status"])
    assert "WO_SHORTAGE" not in codes(company)
    enable(tenant_a, "MFG_PLANNING")
    assert "WO_SHORTAGE" in codes(company)


def test_a_batch_left_on_hold_and_an_overdue_quality_problem_surface_with_the_quality_switch(tenant_a):
    from inventory.models import BatchLot
    from quality.models import NonConformance

    company = prepare(tenant_a)
    prod = make_product(company, sku="Q-1", track_batch=True)
    lot = BatchLot.objects.create(company=company, product=prod, batch_no="HOLD-1", quality_status="HOLD")
    BatchLot.objects.filter(pk=lot.pk).update(updated_at=timezone.now() - timedelta(days=12))
    NonConformance.objects.create(
        company=company, number="NCR-1", description="Bad seal", status="OPEN",
        due_date=timezone.localdate() - timedelta(days=2), created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    assert not {"BATCH_ON_HOLD", "NCR_OVERDUE"} & set(codes(company))
    enable(tenant_a, "MFG_QUALITY")
    found = set(codes(company))
    assert {"BATCH_ON_HOLD", "NCR_OVERDUE"} <= found


def test_a_dismissal_of_a_manufacturing_row_is_accepted(tenant_a):
    from insights.outcomes import code_for_key

    assert code_for_key("WO_LATE:12") == "WO_LATE"
    assert "WO_LATE" in KNOWN_CODES


def test_a_waiting_extra_material_request_raises_a_row_until_it_is_decided(tenant_a):
    from manufacturing.services import issue as issue_svc

    company = prepare(tenant_a, separate=True)
    raw = stocked(tenant_a, "ATT-APR", 1000, 5)
    fg = make_product(company, sku="ATT-APR-FG")
    bom = make_bom(company, fg, [(raw, 1)], user=tenant_a.owner)
    wo = release_work_order(make_wo(company, bom, 10, user=tenant_a.owner), tenant_a.owner)
    draft = issue_svc.create_issue(wo, tenant_a.owner, [{"wo_line": wo.component_lines.first(), "qty": 30, "extra_reason": "Spill"}])
    assert "WO_APPROVAL_WAITING" not in codes(company)              # nobody has asked yet
    issue_svc.request_approval(draft, tenant_a.owner, "need it")
    cache.clear()
    rows = [r for r in build_attention_rows(company, None) if r["code"] == "WO_APPROVAL_WAITING"]
    assert len(rows) == 1
    assert rows[0]["dedupe_key"] == f"WO_APPROVAL_WAITING:{draft.pk}"
    assert rows[0]["action_href"] == f"/manufacturing/work-orders/{wo.pk}"
    issue_svc.decide_approval(draft, tenant_a.owner, approve=False, note="use leftovers")
    assert "WO_APPROVAL_WAITING" not in codes(company)               # turned down: no longer waiting
