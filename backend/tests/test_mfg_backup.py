"""A tenant backup carries, wipes and restores the quality, job work, planning and shop-floor tables."""

from decimal import Decimal

import pytest

from accounts.tenant_backup import build_export_payload, restore_destroy_in_place
from jobwork.models import JobWorkChallan, JobWorkChallanLine, JobWorkOrder
from jobwork.services import out
from manufacturing.models import (
    DowntimeReason, JobCard, Machine, MrpRun, Operator, RoutingOperation, StandardCost, WorkCentre,
)
from manufacturing.services import release_work_order, shopfloor
from quality.models import DefectCode, Inspection, InspectionParameter, InspectionResult, InspectionTemplate, NonConformance
from quality.services import create_inspection, raise_ncr
from tests.conftest import make_product, make_supplier
from tests.mfg_helpers import make_bom, make_wo, prepare, stocked

pytestmark = pytest.mark.django_db(transaction=True)

SWITCHES = ("MFG_PLANNING", "MFG_QUALITY", "MFG_JOB_WORK", "MFG_SHOP_FLOOR", "MFG_COSTING_GL")


def D(v):
    return Decimal(str(v))


def build(tenant):
    company = prepare(tenant)
    flags = dict(company.feature_flags or {})
    flags.update({k: True for k in SWITCHES})
    company.feature_flags = flags
    company.save(update_fields=["feature_flags"])
    raw = stocked(tenant, "BK2-RAW", 200, 10)
    fg = make_product(company, sku="BK2-FG")
    bom = make_bom(company, fg, [(raw, 2)], user=tenant.owner)
    # shop floor
    wc = WorkCentre.objects.create(company=company, code="CUT", name="Cutting", created_by=tenant.owner, updated_by=tenant.owner)
    shopfloor.set_routing(bom, [{"work_centre": wc, "name": "Cut", "run_minutes_per_unit": "2"}], tenant.owner)
    wo = make_wo(company, bom, 10, user=tenant.owner)
    release_work_order(wo, tenant.owner)
    shopfloor.create_job_cards(wo, tenant.owner)
    shopfloor.create_operator(company, tenant.owner, code="OP1", name="Asha", pin="4821")
    reason = DowntimeReason.objects.create(company=company, code="JAM", name="Jam", created_by=tenant.owner, updated_by=tenant.owner)
    Machine.objects.create(company=company, code="M1", name="Press", work_centre=wc, created_by=tenant.owner, updated_by=tenant.owner)
    StandardCost.objects.create(company=company, product=fg, effective_from="2026-04-01", material=D(20), created_by=tenant.owner, updated_by=tenant.owner)
    MrpRun.objects.create(company=company, number="MRP-1", as_of="2026-10-20", horizon_days=30, created_by=tenant.owner, updated_by=tenant.owner)
    # quality
    tpl = InspectionTemplate.objects.create(company=company, name="Final", product=fg, stage="FINAL", created_by=tenant.owner, updated_by=tenant.owner)
    InspectionParameter.objects.create(template=tpl, company=company, name="Colour", kind="PASS_FAIL", sequence=0)
    DefectCode.objects.create(company=company, code="D1", name="Scratch", created_by=tenant.owner, updated_by=tenant.owner)
    insp = create_inspection(company, tenant.owner, product=fg, qty=5, source_type="MANUAL", stage="FINAL", template=tpl)
    raise_ncr(insp, tenant.owner, source="INSPECTION")
    # job work
    sup = make_supplier(company, name="Ravi Dyers")
    order = out.create_order(company, tenant.owner, supplier=sup, process="Dyeing")
    ch = out.create_challan(order, tenant.owner, [{"product": raw, "qty": 50}])
    out.issue_challan(ch, tenant.owner)
    return company, {"reason": reason}


def counts(company):
    return {
        "centres": WorkCentre.objects.filter(company=company).count(),
        "routing": RoutingOperation.objects.filter(company=company).count(),
        "cards": JobCard.objects.filter(company=company).count(),
        "operators": Operator.objects.filter(company=company).count(),
        "machines": Machine.objects.filter(company=company).count(),
        "std": StandardCost.objects.filter(company=company).count(),
        "mrp": MrpRun.objects.filter(company=company).count(),
        "templates": InspectionTemplate.objects.filter(company=company).count(),
        "params": InspectionParameter.objects.filter(company=company).count(),
        "inspections": Inspection.objects.filter(company=company).count(),
        "results": InspectionResult.objects.filter(company=company).count(),
        "ncr": NonConformance.objects.filter(company=company).count(),
        "jw_orders": JobWorkOrder.objects.filter(company=company).count(),
        "jw_challans": JobWorkChallan.objects.filter(company=company).count(),
        "jw_lines": JobWorkChallanLine.objects.filter(company=company).count(),
    }


def test_the_backup_carries_every_new_table(tenant_a):
    company, _ = build(tenant_a)
    payload = build_export_payload(company)
    for key in (
        "mfg_work_centres", "mfg_routing_operations", "mfg_job_cards", "mfg_operators", "mfg_standard_costs",
        "mfg_mrp_runs", "quality_templates", "quality_inspections", "quality_results", "quality_ncrs",
        "jw_orders", "jw_challans", "jw_challan_lines",
    ):
        assert payload.get(key), key


def test_restoring_over_a_company_with_these_rows_neither_fails_nor_loses_them(tenant_a):
    company, _ = build(tenant_a)
    before = counts(company)
    assert all(v >= 1 for v in before.values()), before
    payload = build_export_payload(company)
    restore_destroy_in_place(company=company, payload=payload, owner=tenant_a.owner, confirm_destroy_unbacked=True)
    assert counts(company) == before
    # The restored challan still points at the restored order and job worker godown.
    ch = JobWorkChallan.objects.get(company=company)
    assert ch.order.supplier is not None and ch.lines.get().product.sku == "BK2-RAW"
    card = JobCard.objects.get(company=company)
    assert card.work_order.company_id == company.pk and card.work_centre.code == "CUT"
    from django.contrib.auth.hashers import check_password

    assert check_password("4821", Operator.objects.get(company=company).pin_hash)


def test_deleting_a_company_with_these_rows_does_not_hit_a_protected_row(tenant_a):
    from accounts.tenant_backup import wipe_logical_tenant_rows
    from core.rls import rls_bypass

    company, _ = build(tenant_a)
    with rls_bypass():
        wipe_logical_tenant_rows(company)
    assert all(v == 0 for v in counts(company).values())
