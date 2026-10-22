"""Depth tests (phase 1 of the test plan), last batch: recipe rules and import rows, quality rules and forms, job-work
helpers, and the planning and report endpoints' own checks."""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from core.exceptions import BusinessRuleError
from inventory.models import BatchLot, MovementType, SerialNumber
from inventory.services import InventoryService, SerialNumberService
from jobwork.services import common as jw_common
from jobwork.services import out
from manufacturing.services import bom as bom_svc
from manufacturing.services import bom_import
from quality import services as qc
from quality.models import InspectionParameter, InspectionTemplate
from tests.conftest import make_product, make_supplier
from tests.mfg_helpers import make_bom, member, prepare, stocked

pytestmark = pytest.mark.django_db

M, Q, J = "/api/v1/manufacturing", "/api/v1/quality", "/api/v1/jobwork"


def D(v):
    return Decimal(str(v))


def code(exc):
    return exc.value.get_codes()


def data_of(resp):
    return json.loads(resp.content)["data"]


def flags_on(tenant, *names):
    flags = dict(tenant.company.feature_flags or {})
    flags.update({n: True for n in names})
    tenant.company.feature_flags = flags
    tenant.company.save(update_fields=["feature_flags"])


# --- recipe import: every kind of bad row is named ------------------------------------------------------------------------

HEAD = "row_type,finished_sku,bom_name,output_qty,yield_pct,item_sku,qty,unit,scrap_pct,issue_method,kind,cost_share_pct,recovery_rate\n"


def import_rows(tenant, text, **kw):
    rows = bom_import.parse_file(SimpleUploadedFile("r.csv", (HEAD + text).encode()))
    return bom_import.run_import(tenant.company, tenant.owner, rows, **kw)


@pytest.fixture
def imp(tenant_a):
    company = prepare(tenant_a)
    fg = make_product(company, sku="IM-FG", name="Import FG")
    a = stocked(tenant_a, "IM-A", 10, 5)
    by = make_product(company, sku="IM-BY", name="Import by-product")
    return tenant_a, fg, a, by


def messages(result):
    return [e["message"] for e in result["errors"]]


@pytest.mark.parametrize("line,fragment", [
    ("WRONG,IM-FG,r,,,IM-A,1,,,,,,", "row_type must be LINE or OUTPUT"),
    ("LINE,NOPE,r,,,IM-A,1,,,,,,", "finished_sku 'NOPE' is not a product"),
    ("LINE,IM-FG,r,,,NOPE,1,,,,,,", "item_sku 'NOPE' is not a product"),
    ("LINE,IM-FG,r,,,IM-A,0,,,,,,", "qty must be above zero"),
    ("LINE,IM-FG,r,,,IM-A,,,,,,,", "qty must be above zero"),
    ("LINE,IM-FG,r,,,IM-A,1,furlong,,,,,", "unit 'furlong' does not exist"),
    ("LINE,IM-FG,r,,,IM-A,1,,x,,,,", "'x' is not a number"),
    ("LINE,IM-FG,r,,,IM-A,1,,,SOMETIMES,,,", "issue_method must be MANUAL or BACKFLUSH"),
    ("OUTPUT,IM-FG,r,,,IM-BY,1,,,,SPECIAL,,", "kind must be CO_PRODUCT, BY_PRODUCT or SCRAP"),
])
def test_each_kind_of_bad_row_is_named(imp, line, fragment):
    tenant, *_ = imp
    result = import_rows(tenant, line + "\n", commit=True)
    assert any(fragment in m for m in messages(result)), messages(result)
    assert result["created"] == 0 and result["committed"] is False                     # nothing is saved with errors in it


def test_a_recipe_with_only_outputs_is_refused_and_one_with_bad_content_says_why(imp):
    tenant, fg, a, by = imp
    only_out = import_rows(tenant, "OUTPUT,IM-FG,r,,,IM-BY,1,,,,BY_PRODUCT,,2\n")
    assert any("has no material rows" in m for m in messages(only_out))
    bad_yield = import_rows(tenant, "LINE,IM-FG,r,1,150,IM-A,1,,,,,,\n")
    assert any("Yield" in m for m in messages(bad_yield))
    share = import_rows(tenant, "LINE,IM-FG,r,1,100,IM-A,1,,,,,,\nOUTPUT,IM-FG,r,1,100,IM-BY,1,,,,BY_PRODUCT,20,\n")
    assert any("cost share" in m.lower() for m in messages(share))


def test_an_import_can_leave_the_new_recipe_as_a_draft(imp):
    tenant, fg, a, by = imp
    result = import_rows(tenant, "LINE,IM-FG,r,1,100,IM-A,2,,,,,,\n", commit=True, activate=False)
    assert result["committed"] and result["created"] == 1
    from manufacturing.models import Bom

    assert Bom.objects.get(product=fg).status == "DRAFT"


def test_a_file_with_nothing_in_it_is_refused(tenant_a):
    with pytest.raises(BusinessRuleError) as exc:
        bom_import.parse_file(SimpleUploadedFile("e.csv", b"\n\n"))
    assert code(exc) == "MFG_IMPORT_EMPTY"


# --- recipe rules ---------------------------------------------------------------------------------------------------------

def test_a_recipe_is_checked_before_anything_is_written(tenant_a):
    company = prepare(tenant_a)
    fg = make_product(company, sku="VC-FG")
    comp = stocked(tenant_a, "VC-C", 10, 5)
    other = make_product(company, sku="VC-OUT")

    def check(lines=None, outputs=None, **kw):
        bom_svc.validate_content(company, fg, lines if lines is not None else [{"component": comp}], outputs or [], **kw)

    check()
    for kw, expect in (({"output_qty": 0}, "MFG_BAD_BATCH_SIZE"), ({"yield_pct": 0}, "MFG_BAD_YIELD"), ({"yield_pct": 101}, "MFG_BAD_YIELD")):
        with pytest.raises(BusinessRuleError) as exc:
            check(**kw)
        assert code(exc) == expect
    with pytest.raises(BusinessRuleError) as exc:
        check(lines=[{"component": comp, "scrap_pct": 100}])
    assert code(exc) == "MFG_BAD_SCRAP_PCT"
    for outputs, expect in (
        ([{"product": fg, "kind": "BY_PRODUCT"}], "MFG_OUTPUT_IS_MAIN"),
        ([{"product": comp, "kind": "BY_PRODUCT"}], "MFG_OUTPUT_IS_COMPONENT"),
        ([{"product": other, "kind": "BY_PRODUCT", "cost_share_pct": 5}], "MFG_BAD_COST_SHARE"),
        ([{"product": other, "kind": "CO_PRODUCT", "cost_share_pct": 70}, {"product": make_product(company, sku="VC-OUT2"), "kind": "CO_PRODUCT", "cost_share_pct": 40}], "MFG_BAD_COST_SHARE"),
    ):
        with pytest.raises(BusinessRuleError) as exc:
            check(outputs=outputs)
        assert code(exc) == expect


def test_a_recipe_revision_copies_its_materials_outputs_and_costs_and_a_later_start_is_refused(tenant_a):
    company = prepare(tenant_a)
    fg = make_product(company, sku="RV2-FG")
    comp = stocked(tenant_a, "RV2-C", 10, 5)
    by = make_product(company, sku="RV2-BY")
    first = make_bom(
        company, fg, [(comp, 2)], user=tenant_a.owner, outputs=[{"product": by, "kind": "BY_PRODUCT", "qty": D("0.5")}],
        additional=[{"label": "Labour", "element": "LABOUR", "basis": "PER_BATCH", "amount": D(40)}],
    )
    revised = bom_svc.create_revision(first, tenant_a.owner, "less of it")
    assert revised.lines.count() == 1 and revised.outputs.count() == 1 and revised.additional_costs.count() == 1
    assert revised.revision_no == first.revision_no + 1 and revised.status == "DRAFT"
    first.refresh_from_db()
    first.effective_from = timezone.localdate() + timedelta(days=10)
    first.save(update_fields=["effective_from"])
    with pytest.raises(BusinessRuleError) as exc:
        bom_svc.activate_revision(revised, tenant_a.owner)                                  # would start before an active one that starts later
    assert code(exc) == "MFG_REVISION_OVERLAP"


# --- quality rules --------------------------------------------------------------------------------------------------------

def quality_world(tenant):
    company = prepare(tenant)
    flags_on(tenant, "MFG_QUALITY")
    product = make_product(company, sku="QL-P", track_batch=True)
    tpl = InspectionTemplate.objects.create(company=company, name="Q", stage="FINAL", sample_size=1)
    InspectionParameter.objects.create(company=company, template=tpl, name="Weight", kind="NUMERIC", min_value=9, max_value=11, mandatory=True)
    InspectionParameter.objects.create(company=company, template=tpl, name="Colour", kind="PASS_FAIL", mandatory=False)
    InspectionParameter.objects.create(company=company, template=tpl, name="Remark", kind="TEXT", mandatory=False)
    return company, product, tpl


def test_results_are_judged_by_kind_and_unrecorded_ones_stay_open(tenant_a):
    company, product, tpl = quality_world(tenant_a)
    insp = qc.create_inspection(company, tenant_a.owner, product=product, qty=10, source_type="INTERNAL", stage="FINAL", template=tpl)
    by_name = {r.name: r for r in insp.results.all()}
    qc.record_results(insp, tenant_a.owner, {str(by_name["Weight"].pk): "", str(by_name["Colour"].pk): "ok", str(by_name["Remark"].pk): "fine"})
    for r in insp.results.all():
        r.refresh_from_db()
    assert by_name["Weight"].passed is None and by_name["Colour"].pk
    colour = insp.results.get(name="Colour")
    assert colour.passed is True and insp.results.get(name="Remark").passed is None
    qc.record_results(insp, tenant_a.owner, {str(colour.pk): "no"})
    assert insp.results.get(name="Colour").passed is False
    with pytest.raises(BusinessRuleError) as exc:
        qc.complete_inspection(insp, tenant_a.owner)                                          # the mandatory weight was never recorded
    assert code(exc) == "QC_INCOMPLETE"


def test_a_result_that_belongs_to_another_inspection_is_refused(tenant_a):
    company, product, tpl = quality_world(tenant_a)
    one = qc.create_inspection(company, tenant_a.owner, product=product, qty=1, source_type="INTERNAL", stage="FINAL", template=tpl)
    two = qc.create_inspection(company, tenant_a.owner, product=product, qty=1, source_type="INTERNAL", stage="FINAL", template=tpl)
    with pytest.raises(BusinessRuleError) as exc:
        qc.record_results(one, tenant_a.owner, {str(two.results.first().pk): "10"})
    assert code(exc) == "QC_BAD_RESULT"


def test_a_decision_must_be_one_of_the_four_and_the_accepted_quantity_within_the_lot(tenant_a):
    company, product, tpl = quality_world(tenant_a)
    insp = qc.create_inspection(company, tenant_a.owner, product=product, qty=10, source_type="INTERNAL", stage="FINAL", template=tpl)
    qc.record_results(insp, tenant_a.owner, {str(insp.results.get(name="Weight").pk): "10"})
    with pytest.raises(BusinessRuleError) as exc:
        qc.complete_inspection(insp, tenant_a.owner, decision="MAYBE")
    assert code(exc) == "QC_BAD_DECISION"
    for bad in (-1, 11):
        with pytest.raises(BusinessRuleError) as exc:
            qc.complete_inspection(insp, tenant_a.owner, qty_accepted=bad)
        assert code(exc) == "QC_BAD_QTY"
    done = qc.complete_inspection(insp, tenant_a.owner)
    assert done.decision == "PASS" and done.qty_accepted == D(10)
    with pytest.raises(BusinessRuleError) as exc:
        qc.complete_inspection(done, tenant_a.owner)
    assert code(exc) == "QC_NOT_DRAFT"
    with pytest.raises(BusinessRuleError) as exc:
        qc.record_results(done, tenant_a.owner, {})
    assert code(exc) == "QC_NOT_DRAFT"


def test_a_failed_result_can_be_passed_only_by_a_manager(tenant_a):
    company, product, tpl = quality_world(tenant_a)
    insp = qc.create_inspection(company, tenant_a.owner, product=product, qty=10, source_type="INTERNAL", stage="FINAL", template=tpl)
    qc.record_results(insp, tenant_a.owner, {str(insp.results.get(name="Weight").pk): "20"})
    with pytest.raises(BusinessRuleError) as exc:
        qc.complete_inspection(insp, tenant_a.owner, decision="PASS", is_manager=False)
    assert code(exc) == "QC_PASS_NEEDS_MANAGER"
    assert qc.complete_inspection(insp, tenant_a.owner, decision="PASS", is_manager=True).decision == "PASS"


def test_a_hold_decision_keeps_the_lot_held_and_a_partial_pass_raises_a_problem_for_the_rest(tenant_a):
    company, product, tpl = quality_world(tenant_a)
    lot = BatchLot.objects.create(company=company, product=product, batch_no="QH-1")
    InventoryService.post_movement(company=company, product=product, batch=lot, movement_type=MovementType.PURCHASE, quantity=D(10), unit_cost=D(5), user=tenant_a.owner, reference_type="t", reference_id="1")
    qc.set_batch_status(lot, "HOLD", tenant_a.owner, "awaiting")
    held = qc.create_inspection(company, tenant_a.owner, product=product, qty=10, source_type="BATCH", stage="FINAL", batch=lot, template=tpl)
    qc.record_results(held, tenant_a.owner, {str(held.results.get(name="Weight").pk): "10"})
    qc.complete_inspection(held, tenant_a.owner, decision="HOLD")
    lot.refresh_from_db()
    assert lot.quality_status == "HOLD"
    again = qc.create_inspection(company, tenant_a.owner, product=product, qty=10, source_type="BATCH", stage="FINAL", batch=lot, template=tpl)
    qc.record_results(again, tenant_a.owner, {str(again.results.get(name="Weight").pk): "10"})
    qc.complete_inspection(again, tenant_a.owner, decision="PASS", qty_accepted=D(7))
    from quality.models import NonConformance

    assert NonConformance.objects.filter(company=company, inspection=again).exists()           # the 3 that were not accepted
    lot.refresh_from_db()
    assert lot.quality_status == "RELEASED"


def test_a_batch_status_must_be_a_known_one_and_changing_it_to_itself_changes_nothing(tenant_a):
    company, product, tpl = quality_world(tenant_a)
    lot = BatchLot.objects.create(company=company, product=product, batch_no="QS-1")
    with pytest.raises(BusinessRuleError) as exc:
        qc.set_batch_status(lot, "WHATEVER", tenant_a.owner)
    assert code(exc) == "QC_BAD_STATUS"
    assert qc.set_batch_status(lot, lot.quality_status, tenant_a.owner) is lot


def test_the_forms_refuse_a_duplicate_defect_code_and_an_impossible_checklist(tenant_a):
    prepare(tenant_a)
    flags_on(tenant_a, "MFG_QUALITY")
    c = tenant_a.client
    assert c.post(f"{Q}/defect-codes/", {"code": " crk ", "name": "Crack"}, format="json").status_code == 201
    dup = c.post(f"{Q}/defect-codes/", {"code": "CRK", "name": "Other"}, format="json")
    assert dup.status_code == 400
    mine = data_of(c.get(f"{Q}/defect-codes/"))
    first = mine["results"][0] if isinstance(mine, dict) else mine[0]
    assert first["code"] == "CRK"                                                         # saved tidy
    assert c.patch(f"{Q}/defect-codes/{first['id']}/", {"code": "crk"}, format="json").status_code == 200      # its own code is not a clash
    backwards = c.post(f"{Q}/templates/", {"name": "T", "stage": "FINAL", "parameters": [{"name": "W", "kind": "NUMERIC", "minValue": "11", "maxValue": "9"}]}, format="json")
    assert backwards.status_code == 400
    limitless = c.post(f"{Q}/templates/", {"name": "T", "stage": "FINAL", "parameters": [{"name": "W", "kind": "NUMERIC"}]}, format="json")
    assert limitless.status_code == 400


def test_replacing_a_checklist_replaces_its_checks_but_not_past_inspections(tenant_a):
    company, product, tpl = quality_world(tenant_a)
    insp = qc.create_inspection(company, tenant_a.owner, product=product, qty=1, source_type="INTERNAL", stage="FINAL", template=tpl)
    c = tenant_a.client
    resp = c.patch(f"{Q}/templates/{tpl.pk}/", {"parameters": [{"name": "Length", "kind": "NUMERIC", "minValue": "1", "maxValue": "2"}]}, format="json")
    assert resp.status_code == 200
    assert list(tpl.parameters.values_list("name", flat=True)) == ["Length"]
    assert insp.results.count() == 3                                                      # the inspection kept its own copy


# --- job work helpers -----------------------------------------------------------------------------------------------------

def test_a_job_worker_godown_is_made_once_and_gets_a_free_code(tenant_a):
    from inventory.models import Warehouse

    company = prepare(tenant_a)
    sup = make_supplier(company, name="Godown Worker")
    wh = jw_common.ensure_job_worker_warehouse(company, sup)
    assert wh.kind == "JOB_WORKER" and wh.job_worker_id == sup.pk and wh.name == "At Godown Worker"
    assert jw_common.ensure_job_worker_warehouse(company, sup).pk == wh.pk
    Warehouse.objects.filter(pk=wh.pk).update(job_worker=None)                            # the link is lost; the code is still taken
    again = jw_common.ensure_job_worker_warehouse(company, sup)
    assert again.pk != wh.pk and again.code.startswith(f"JW{sup.pk}-")


@pytest.mark.invariant_skip("inventory.serial_traceability", reason="serial rows are created directly through the ORM, without a godown or movement")
def test_serial_goods_move_to_the_job_workers_godown_only_when_they_are_available_at_the_source(tenant_a):
    company = prepare(tenant_a)
    comp = make_product(company, sku="JS-C", track_serial=True, purchase_price="20")
    InventoryService.post_movement(company=company, product=comp, movement_type=MovementType.OPENING_STOCK, quantity=D(2), unit_cost=D(20), user=tenant_a.owner)
    src = InventoryService.default_warehouse(company)
    SerialNumberService.receive(company=company, product=comp, warehouse=src, numbers=["JS-1", "JS-2"], quantity=D(2), user=tenant_a.owner)
    dst = jw_common.ensure_job_worker_warehouse(company, make_supplier(company, name="Serial Worker"))
    jw_common.move_serials(company, comp, [" JS-1 ", ""], src, dst)
    assert SerialNumber.objects.get(company=company, serial_number="JS-1").warehouse_id == dst.pk
    with pytest.raises(BusinessRuleError) as exc:
        jw_common.move_serials(company, comp, ["JS-1"], src, dst)                         # it is no longer at the source
    assert code(exc) == "JW_SERIAL_UNAVAILABLE"
    with pytest.raises(BusinessRuleError):
        jw_common.move_serials(company, comp, ["NOPE"], src, dst)


def test_job_work_documents_refuse_empty_unknown_and_foreign_things(tenant_a, tenant_b):
    company = prepare(tenant_a)
    flags_on(tenant_a, "MFG_JOB_WORK")
    raw = stocked(tenant_a, "JD-RAW", 50, 10)
    sup = make_supplier(company, name="Doc Worker")
    foreign = make_supplier(tenant_b.company, name="Not Ours")
    with pytest.raises(BusinessRuleError) as exc:
        out.create_order(company, tenant_a.owner, supplier=None)
    assert code(exc) == "JW_BAD_REFERENCE"
    with pytest.raises(BusinessRuleError) as exc:
        out.create_order(company, tenant_a.owner, supplier=foreign)
    assert code(exc) == "JW_BAD_REFERENCE"
    order = out.create_order(company, tenant_a.owner, supplier=sup)
    for lines, expect in (([], "JW_EMPTY_DOC"), ([{"product": raw, "qty": 0}], "JW_BAD_QTY"), ([{"qty": 1}], "JW_BAD_REFERENCE")):
        with pytest.raises(BusinessRuleError) as exc:
            out.create_challan(order, tenant_a.owner, lines)
        assert code(exc) == expect
    ch = out.create_challan(order, tenant_a.owner, [{"product": raw, "qty": 5}])
    out.issue_challan(ch, tenant_a.owner)
    with pytest.raises(BusinessRuleError) as exc:
        out.issue_challan(ch, tenant_a.owner)
    assert code(exc) == "JW_DOC_NOT_DRAFT"
    for lines, expect in (
        ([], "JW_EMPTY_DOC"),
        ([{"kind": "MYSTERY", "product": raw, "qty": 1}], "JW_BAD_KIND"),
        ([{"kind": "PROCESSED", "product": raw, "qty": 1}], "JW_BAD_QTY"),                    # no material used named
        ([{"kind": "UNPROCESSED_RETURN", "product": raw, "qty": 0}], "JW_BAD_QTY"),
        ([{"kind": "UNPROCESSED_RETURN", "qty": 1}], "JW_BAD_REFERENCE"),
    ):
        with pytest.raises(BusinessRuleError) as exc:
            out.create_receipt(order, tenant_a.owner, lines)
        assert code(exc) == expect, lines
    over = out.create_receipt(order, tenant_a.owner, [{"kind": "UNPROCESSED_RETURN", "product": raw, "qty": 99}])
    with pytest.raises(BusinessRuleError) as exc:
        out.post_receipt(over, tenant_a.owner)
    assert code(exc) == "JW_OVER_RETURN"


@pytest.mark.invariant_skip("jobwork.stock_at_job_worker_matches_open_challans", reason="the sale invoice from the job worker's godown that takes the stock out is not raised in this test")
def test_goods_sent_on_to_another_job_worker_and_direct_supply_follow_their_rules(tenant_a):
    company = prepare(tenant_a)
    flags_on(tenant_a, "MFG_JOB_WORK")
    raw = stocked(tenant_a, "JO-RAW", 100, 10)
    first = out.create_order(company, tenant_a.owner, supplier=make_supplier(company, name="First"))
    second = out.create_order(company, tenant_a.owner, supplier=make_supplier(company, name="Second"))
    out.issue_challan(out.create_challan(first, tenant_a.owner, [{"product": raw, "qty": 20}]), tenant_a.owner)
    no_target = out.create_receipt(first, tenant_a.owner, [{"kind": "SENT_TO_OTHER", "product": raw, "qty": 5}])
    with pytest.raises(BusinessRuleError) as exc:
        out.post_receipt(no_target, tenant_a.owner)
    assert code(exc) == "JW_BAD_REFERENCE"
    onward = out.create_receipt(first, tenant_a.owner, [{"kind": "SENT_TO_OTHER", "product": raw, "qty": 5, "other_order": second.pk}])
    out.post_receipt(onward, tenant_a.owner)
    assert second.challans.filter(origin="FROM_OTHER_JOB_WORKER").exists()
    undeclared = out.create_receipt(first, tenant_a.owner, [{"kind": "SUPPLIED_FROM_JW", "product": raw, "qty": 5, "invoice_ref": "INV-1"}])
    with pytest.raises(BusinessRuleError) as exc:
        out.post_receipt(undeclared, tenant_a.owner)
    assert code(exc) == "JW_DIRECT_SUPPLY_NOT_DECLARED"
    declared = out.create_order(company, tenant_a.owner, supplier=make_supplier(company, name="Direct"), direct_supply_declared=True)
    out.issue_challan(out.create_challan(declared, tenant_a.owner, [{"product": raw, "qty": 10}]), tenant_a.owner)
    no_invoice = out.create_receipt(declared, tenant_a.owner, [{"kind": "SUPPLIED_FROM_JW", "product": raw, "qty": 5}])
    with pytest.raises(BusinessRuleError) as exc:
        out.post_receipt(no_invoice, tenant_a.owner)
    assert code(exc) == "JW_INVOICE_REQUIRED"
    ok = out.create_receipt(declared, tenant_a.owner, [{"kind": "SUPPLIED_FROM_JW", "product": raw, "qty": 5, "invoice_ref": "INV-9"}])
    assert out.post_receipt(ok, tenant_a.owner).status == "POSTED"


# --- planning and report endpoints ----------------------------------------------------------------------------------------

def test_the_planning_endpoints_say_what_they_need(tenant_a):
    from manufacturing import demo

    built = demo.build(tenant_a.company, tenant_a.owner)
    flags_on(tenant_a, "MFG_PLANNING", "MFG_COSTING_GL")
    c = tenant_a.client
    biscuit = built["biscuit"]
    assert c.get(f"{M}/explode/").status_code == 400                                   # no item named
    assert c.get(f"{M}/explode/?product=999999").status_code in (400, 404)
    got = c.get(f"{M}/explode/?product={biscuit.pk}&qty=10&expand=all")
    assert got.status_code == 200
    assert c.get(f"{M}/explode/?product={biscuit.pk}&qty=abc").status_code == 400
    assert c.get(f"{M}/where-used/?product={built['flour'].pk}").status_code == 200
    assert c.get(f"{M}/cost-rollup/?product={biscuit.pk}&qty=10&method=CURRENT").status_code == 200
    assert c.get(f"{M}/can-make/?product={biscuit.pk}").status_code == 200
    assert c.get(f"{M}/atp/?product={biscuit.pk}&date=2027-01-01").status_code == 200
    assert c.get(f"{M}/atp/?product={biscuit.pk}&date=someday").status_code == 400
    assert c.get(f"{M}/shortages/").status_code == 200 and c.get(f"{M}/board/").status_code == 200
    assert c.get(f"{M}/sales-order-status/").status_code in (200, 400, 404)
    _u, floor = member(tenant_a, "INVENTORY_STAFF", can_manage_inventory=True)
    assert floor.get(f"{M}/cost-rollup/?product={biscuit.pk}").status_code == 403                # costs are not for the floor


def test_set_priority_checks_its_values(tenant_a):
    from manufacturing.services import release_work_order
    from tests.mfg_helpers import make_wo

    company = prepare(tenant_a, separate=True)
    flags_on(tenant_a, "MFG_PLANNING")
    raw = stocked(tenant_a, "SP-RAW", 100, 5)
    fg = make_product(company, sku="SP-FG")
    wo = release_work_order(make_wo(company, make_bom(company, fg, [(raw, 1)], user=tenant_a.owner), 5, user=tenant_a.owner), tenant_a.owner)
    c = tenant_a.client
    url = f"{M}/work-orders/{wo.pk}/set-priority/"
    assert c.post(url, {"priority": 0}, format="json").status_code == 400
    assert c.post(url, {"priority": "high"}, format="json").status_code == 400
    assert c.post(url, {"priority": 2, "delayReason": "NOT_A_REASON"}, format="json").status_code == 400
    assert c.post(url, {"priority": 2, "dueDate": "next week"}, format="json").status_code == 400
    ok = c.post(url, {"priority": 2, "delayReason": "MATERIAL_SHORTAGE", "dueDate": str(timezone.localdate() + timedelta(days=3))}, format="json")
    assert ok.status_code == 200, ok.content[:300]
    assert c.post(f"{M}/work-orders/999999/set-priority/", {"priority": 2}, format="json").status_code == 400


def test_reports_export_as_csv_and_refuse_unknown_ones(tenant_a):
    from manufacturing import demo

    demo.build(tenant_a.company, tenant_a.owner)
    flags_on(tenant_a, "MFG_COSTING_GL")
    c = tenant_a.client
    assert c.get(f"{M}/reports/nope/").status_code in (400, 404)
    for slug in ("wip", "work-order-cost", "variance", "yield-wastage", "consumption", "output", "on-time", "scrap-register", "profitability", "reconciliation"):
        assert c.get(f"{M}/reports/{slug}/?from=2026-04-01&to=2026-10-31&as_of=2026-10-31").status_code == 200, slug
        csv_resp = c.get(f"{M}/reports/{slug}/?from=2026-04-01&to=2026-10-31&as_of=2026-10-31&export=csv")
        assert csv_resp.status_code == 200 and csv_resp["Content-Type"].startswith("text/csv"), slug
    assert c.get(f"{M}/reports/profitability/?from=2026-04-01&to=2026-10-31&by=customer").status_code == 200
    _u, floor = member(tenant_a, "INVENTORY_STAFF", can_manage_inventory=True)
    assert floor.get(f"{M}/reports/wip/").status_code == 403                                 # costs are not for the floor
