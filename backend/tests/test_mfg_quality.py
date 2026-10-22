"""Manufacturing phase 3: batch holds, inspections, non-conformances, supplier scorecard, certificate."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.invariants import assert_all_invariants
from inventory.models import BatchLot, MovementType, StockBalance, Warehouse
from inventory.services import InventoryService, InventoryValuationService
from purchases.grn_service import GoodsReceiptService
from purchases.models import GoodsReceipt, GoodsReceiptItem
from quality import services as qc
from quality.models import (
    Inspection, InspectionParameter, InspectionTemplate, NonConformance,
)
from tests.conftest import make_product, make_supplier
from tests.mfg_helpers import body, make_bom, member, prepare, stocked

pytestmark = pytest.mark.django_db


def D(v):
    return Decimal(str(v))


@pytest.fixture(params=["WAVG", "FIFO"])
def method(request):
    return request.param


def quality_on(tenant, **extra):
    flags = dict(tenant.company.feature_flags or {})
    flags["MFG_QUALITY"] = True
    tenant.company.feature_flags = flags
    tenant.company.save(update_fields=["feature_flags"])


def grn(tenant, supplier, product, qty, *, batch_no="", exp=None, price="10", warehouse=None):
    g = GoodsReceipt.objects.create(
        company=tenant.company, supplier=supplier, warehouse=warehouse or InventoryService.default_warehouse(tenant.company), created_by=tenant.owner, updated_by=tenant.owner,
    )
    item = GoodsReceiptItem.objects.create(
        company=tenant.company, goods_receipt=g, product=product, quantity_received=D(qty), quantity_accepted=D(qty),
        quantity_rejected=0, unit_price=D(price), batch_no=batch_no, exp_date=exp,
    )
    return g, item


def template(tenant, product=None, stage="INCOMING", params=()):
    t = InspectionTemplate.objects.create(
        company=tenant.company, name=f"{stage} check", product=product, stage=stage, created_by=tenant.owner, updated_by=tenant.owner,
    )
    for i, p in enumerate(params):
        InspectionParameter.objects.create(template=t, company=tenant.company, sequence=i, **p)
    return t


MOISTURE = {"name": "Moisture", "kind": "NUMERIC", "min_value": D(0), "max_value": D(10), "unit": "%"}
COLOUR = {"name": "Colour", "kind": "PASS_FAIL"}


def results_by_name(insp):
    return {r.name: r for r in insp.results.all()}


# --- templates, results, decisions -----------------------------------------------------------------

def test_results_are_judged_against_their_limits_and_the_decision_follows(tenant_a):
    prepare(tenant_a)
    quality_on(tenant_a)
    product = make_product(tenant_a.company, sku="Q1")
    t = template(tenant_a, product, params=[MOISTURE, COLOUR])
    insp = qc.create_inspection(tenant_a.company, tenant_a.owner, product=product, qty=100, source_type="BATCH", stage="INCOMING", template=t)
    res = results_by_name(insp)
    qc.record_results(insp, tenant_a.owner, {res["Moisture"].pk: "8.5", res["Colour"].pk: "pass"})
    res = results_by_name(insp)
    assert res["Moisture"].passed is True and res["Colour"].passed is True
    # An out-of-range number fails the inspection on its own.
    insp2 = qc.create_inspection(tenant_a.company, tenant_a.owner, product=product, qty=10, source_type="BATCH", stage="INCOMING", template=t)
    r2 = results_by_name(insp2)
    qc.record_results(insp2, tenant_a.owner, {r2["Moisture"].pk: "12", r2["Colour"].pk: "pass"})
    assert results_by_name(insp2)["Moisture"].passed is False


def test_a_template_change_does_not_alter_past_inspections(tenant_a):
    prepare(tenant_a)
    product = make_product(tenant_a.company, sku="Q2")
    t = template(tenant_a, product, params=[MOISTURE])
    insp = qc.create_inspection(tenant_a.company, tenant_a.owner, product=product, qty=1, source_type="BATCH", stage="INCOMING", template=t)
    t.parameters.update(max_value=D(1))
    assert results_by_name(insp)["Moisture"].max_value == D(10)


def test_deciding_needs_every_required_result(tenant_a):
    prepare(tenant_a)
    product = make_product(tenant_a.company, sku="Q3")
    t = template(tenant_a, product, params=[MOISTURE])
    insp = qc.create_inspection(tenant_a.company, tenant_a.owner, product=product, qty=1, source_type="BATCH", stage="INCOMING", template=t)
    with pytest.raises(BusinessRuleError) as exc:
        qc.complete_inspection(insp, tenant_a.owner)
    assert exc.value.get_codes() == "QC_INCOMPLETE"


def test_passing_something_outside_its_limits_is_a_managers_call(tenant_a):
    prepare(tenant_a)
    product = make_product(tenant_a.company, sku="Q4")
    t = template(tenant_a, product, params=[MOISTURE])
    insp = qc.create_inspection(tenant_a.company, tenant_a.owner, product=product, qty=5, source_type="BATCH", stage="INCOMING", template=t)
    qc.record_results(insp, tenant_a.owner, {results_by_name(insp)["Moisture"].pk: "15"})
    with pytest.raises(BusinessRuleError) as exc:
        qc.complete_inspection(insp, tenant_a.owner, decision="PASS", is_manager=False)
    assert exc.value.get_codes() == "QC_PASS_NEEDS_MANAGER"
    done = qc.complete_inspection(insp, tenant_a.owner, decision="PASS", is_manager=True)
    assert done.decision == "PASS"


def test_the_product_template_wins_over_the_generic_one(tenant_a):
    prepare(tenant_a)
    c = tenant_a.company
    product = make_product(c, sku="Q5")
    generic = template(tenant_a, None)
    own = template(tenant_a, product)
    assert qc.find_template(c, product, "INCOMING").pk == own.pk
    assert qc.find_template(c, make_product(c, sku="Q5b"), "INCOMING").pk == generic.pk


# --- incoming material: inspect on the draft goods receipt --------------------------------------------------

def test_a_receipt_for_an_inspected_item_waits_for_its_inspection(tenant_a, method):
    prepare(tenant_a, method=method)
    quality_on(tenant_a)
    c = tenant_a.company
    product = make_product(c, sku="IN1", requires_incoming_inspection=True, purchase_price="10")
    sup = make_supplier(c)
    g, item = grn(tenant_a, sup, product, 100)
    with pytest.raises(BusinessRuleError) as exc:
        GoodsReceiptService.complete(g, tenant_a.owner)
    assert exc.value.get_codes() == "QC_INSPECTION_REQUIRED"
    insp = qc.create_inspection(c, tenant_a.owner, product=product, qty=100, source_type="GRN_ITEM", stage="INCOMING", grn_item=item, supplier=sup)
    qc.complete_inspection(insp, tenant_a.owner, decision="PASS", qty_accepted=D(90))     # 90 good, 10 not
    item.refresh_from_db()
    assert (item.quantity_accepted, item.quantity_rejected) == (D(90), D(10))
    GoodsReceiptService.complete(g, tenant_a.owner)
    assert StockBalance.objects.get(company=c, product=product).on_hand == D(90)         # only what passed enters stock
    ncr = NonConformance.objects.get(company=c, inspection=insp)
    assert ncr.source_type == "GRN" and ncr.qty == D(10) and ncr.supplier_id == sup.pk


def test_a_held_inspection_keeps_the_receipt_waiting(tenant_a, method):
    prepare(tenant_a, method=method)
    quality_on(tenant_a)
    c = tenant_a.company
    product = make_product(c, sku="IN2", requires_incoming_inspection=True)
    sup = make_supplier(c)
    g, item = grn(tenant_a, sup, product, 10)
    insp = qc.create_inspection(c, tenant_a.owner, product=product, qty=10, source_type="GRN_ITEM", stage="INCOMING", grn_item=item, supplier=sup)
    qc.complete_inspection(insp, tenant_a.owner, decision="HOLD")
    with pytest.raises(BusinessRuleError) as exc:
        GoodsReceiptService.complete(g, tenant_a.owner)
    assert exc.value.get_codes() == "QC_INSPECTION_REQUIRED"


def test_with_the_flag_off_nothing_changes_for_a_receipt(tenant_a, method):
    prepare(tenant_a, method=method)
    c = tenant_a.company
    product = make_product(c, sku="IN3", requires_incoming_inspection=True)
    g, item = grn(tenant_a, make_supplier(c), product, 10)
    GoodsReceiptService.complete(g, tenant_a.owner)
    assert StockBalance.objects.get(company=c, product=product).on_hand == D(10)


# --- receive into quarantine ------------------------------------------------------------------------------

def quarantine_world(tenant, method):
    prepare(tenant, method=method)
    quality_on(tenant)
    c = tenant.company
    product = make_product(c, sku="QR1", track_batch=True, receive_into_quarantine=True, purchase_price="20")
    sup = make_supplier(c)
    exp = timezone.localdate() + timedelta(days=200)
    g, item = grn(tenant, sup, product, 100, batch_no="LAB-1", exp=exp, price="20")
    GoodsReceiptService.complete(g, tenant.owner)
    batch = BatchLot.objects.get(company=c, product=product, batch_no="LAB-1")
    return c, product, sup, batch


def test_stock_received_into_quarantine_cannot_be_used(tenant_a, method):
    c, product, sup, batch = quarantine_world(tenant_a, method)
    qrn = Warehouse.objects.get(company=c, kind="QUARANTINE")
    assert batch.quality_status == "QUARANTINE"
    assert StockBalance.objects.get(company=c, product=product, warehouse=qrn).on_hand == D(100)
    # A lab check is waiting for it.
    insp = Inspection.objects.get(company=c, batch=batch)
    assert insp.status == "DRAFT" and insp.source_type == "BATCH"
    for mtype in (MovementType.SALE, MovementType.MANUFACTURE_ISSUE, MovementType.TRANSFER_OUT):
        with pytest.raises(BusinessRuleError) as exc:
            InventoryService.post_movement(
                company=c, product=product, warehouse=qrn, batch=batch, movement_type=mtype, quantity=D(1), unit_cost=D(20),
                user=tenant_a.owner,
            )
        assert exc.value.get_codes() == "MFG_BATCH_ON_HOLD"
    # First-expiry-first-out does not offer it either.
    assert not InventoryValuationService.fefo_batches(c, product, qrn).exists()


def test_the_hold_is_ignored_when_the_flag_is_off(tenant_a, method):
    c, product, sup, batch = quarantine_world(tenant_a, method)
    tenant_a.company.feature_flags = {}
    tenant_a.company.save(update_fields=["feature_flags"])
    qrn = Warehouse.objects.get(company=c, kind="QUARANTINE")
    InventoryService.post_movement(
        company=c, product=product, warehouse=qrn, batch=batch, movement_type=MovementType.SALE, quantity=D(1),
        unit_cost=D(20), user=tenant_a.owner,
    )


def test_passing_the_lab_check_releases_the_lot_and_moves_it_to_the_store(tenant_a, method):
    c, product, sup, batch = quarantine_world(tenant_a, method)
    insp = Inspection.objects.get(company=c, batch=batch)
    done = qc.complete_inspection(insp, tenant_a.owner, decision="PASS")
    batch.refresh_from_db()
    assert batch.quality_status == "RELEASED" and done.qty_accepted == D(100)
    rm = InventoryService.default_warehouse(c)
    assert StockBalance.objects.get(company=c, product=product, warehouse=rm).on_hand == D(100)
    assert StockBalance.objects.get(company=c, product=product, warehouse=Warehouse.objects.get(company=c, kind="QUARANTINE")).on_hand == 0
    # It carried its cost with it.
    assert InventoryValuationService.unit_cost(c, product, rm, batch=batch) == D("20")
    InventoryService.post_movement(
        company=c, product=product, warehouse=rm, batch=batch, movement_type=MovementType.SALE, quantity=D(5),
        unit_cost=D(20), user=tenant_a.owner,
    )
    assert_all_invariants(c)


def test_a_partial_pass_sends_the_rest_to_scrap(tenant_a, method):
    c, product, sup, batch = quarantine_world(tenant_a, method)
    insp = Inspection.objects.get(company=c, batch=batch)
    qc.complete_inspection(insp, tenant_a.owner, decision="PASS", qty_accepted=D(70))
    scrap = Warehouse.objects.get(company=c, kind="SCRAP")
    rm = InventoryService.default_warehouse(c)
    assert StockBalance.objects.get(company=c, product=product, warehouse=rm).on_hand == D(70)
    assert StockBalance.objects.get(company=c, product=product, warehouse=scrap).on_hand == D(30)
    assert NonConformance.objects.filter(company=c, inspection=insp).exists()
    assert_all_invariants(c)


def test_a_failed_lab_check_rejects_the_lot_and_raises_a_non_conformance(tenant_a, method):
    c, product, sup, batch = quarantine_world(tenant_a, method)
    insp = Inspection.objects.get(company=c, batch=batch)
    qc.complete_inspection(insp, tenant_a.owner, decision="FAIL", notes="Out of spec")
    batch.refresh_from_db()
    assert batch.quality_status == "REJECTED"
    scrap = Warehouse.objects.get(company=c, kind="SCRAP")
    assert StockBalance.objects.get(company=c, product=product, warehouse=scrap).on_hand == D(100)
    ncr = NonConformance.objects.get(company=c, inspection=insp)
    assert ncr.supplier_id == sup.pk and ncr.status == "OPEN"
    assert_all_invariants(c)


# --- finished goods ---------------------------------------------------------------------------------------

def test_finished_goods_are_held_until_the_final_inspection(tenant_a, method):
    from manufacturing.services import receipt as receipt_svc, release_work_order, issue as issue_svc
    from tests.mfg_helpers import make_wo

    prepare(tenant_a, method=method)
    quality_on(tenant_a)
    c = tenant_a.company
    fg = make_product(c, sku="FIN1", track_batch=True)
    comp = stocked(tenant_a, "FIN1-C", 100, 5)
    template(tenant_a, fg, stage="FINAL", params=[COLOUR])
    bom = make_bom(c, fg, [(comp, 1)], user=tenant_a.owner)
    wo = release_work_order(make_wo(c, bom, 10, user=tenant_a.owner), tenant_a.owner)
    wl = wo.component_lines.get()
    issue_svc.post_issue(issue_svc.create_issue(wo, tenant_a.owner, [{"wo_line": wl, "qty": 10}]), tenant_a.owner)
    exp = timezone.localdate() + timedelta(days=90)
    rec = receipt_svc.post_receipt(receipt_svc.create_receipt(wo, tenant_a.owner, {"is_final": True, "batch_no": "F-1", "exp_date": exp}), tenant_a.owner)
    batch = BatchLot.objects.get(company=c, product=fg, batch_no="F-1")
    assert batch.quality_status == "HOLD"
    insp = Inspection.objects.get(company=c, receipt_id=rec.pk)
    assert insp.stage == "FINAL" and insp.status == "DRAFT"
    wh = InventoryService.default_warehouse(c)
    with pytest.raises(BusinessRuleError) as exc:
        InventoryService.post_movement(
            company=c, product=fg, warehouse=wh, batch=batch, movement_type=MovementType.SALE, quantity=D(1), unit_cost=D(5),
            user=tenant_a.owner,
        )
    assert exc.value.get_codes() == "MFG_BATCH_ON_HOLD"
    qc.record_results(insp, tenant_a.owner, {results_by_name(insp)["Colour"].pk: "pass"})
    qc.complete_inspection(insp, tenant_a.owner)
    batch.refresh_from_db()
    assert batch.quality_status == "RELEASED"
    InventoryService.post_movement(
        company=c, product=fg, warehouse=wh, batch=batch, movement_type=MovementType.SALE, quantity=D(1), unit_cost=D(5),
        user=tenant_a.owner,
    )


def test_reversing_the_receipt_cancels_its_waiting_inspection(tenant_a, method):
    from manufacturing.services import receipt as receipt_svc, release_work_order, issue as issue_svc
    from tests.mfg_helpers import make_wo

    prepare(tenant_a, method=method)
    quality_on(tenant_a)
    c = tenant_a.company
    fg = make_product(c, sku="FIN2", track_batch=True)
    comp = stocked(tenant_a, "FIN2-C", 100, 5)
    template(tenant_a, fg, stage="FINAL", params=[COLOUR])
    wo = release_work_order(make_wo(c, make_bom(c, fg, [(comp, 1)], user=tenant_a.owner), 10, user=tenant_a.owner), tenant_a.owner)
    wl = wo.component_lines.get()
    issue_svc.post_issue(issue_svc.create_issue(wo, tenant_a.owner, [{"wo_line": wl, "qty": 10}]), tenant_a.owner)
    rec = receipt_svc.post_receipt(receipt_svc.create_receipt(wo, tenant_a.owner, {"is_final": True, "batch_no": "F-2"}), tenant_a.owner)
    receipt_svc.reverse_receipt(rec, tenant_a.owner, "Miscount")
    assert Inspection.objects.get(company=c, receipt_id=rec.pk).status == "CANCELLED"
    assert BatchLot.objects.get(company=c, batch_no="F-2").quality_status == "RELEASED"


# --- non-conformance and scorecard ---------------------------------------------------------------------------

def test_a_non_conformance_moves_one_step_at_a_time(tenant_a):
    prepare(tenant_a)
    c = tenant_a.company
    ncr = NonConformance.objects.create(company=c, number="NCR-1", source_type="INTERNAL", created_by=tenant_a.owner, updated_by=tenant_a.owner)
    with pytest.raises(BusinessRuleError) as exc:
        qc.advance_ncr(ncr, tenant_a.owner, status="CLOSED")
    assert exc.value.get_codes() == "QC_NCR_ORDER"
    with pytest.raises(BusinessRuleError) as exc:
        qc.advance_ncr(ncr, tenant_a.owner, status="ACTION")
    assert exc.value.get_codes() == "QC_NCR_NEEDS_CAUSE"
    qc.advance_ncr(ncr, tenant_a.owner, status="ACTION", root_cause="Worn blade")
    with pytest.raises(BusinessRuleError) as exc:
        qc.advance_ncr(ncr, tenant_a.owner, status="VERIFIED")
    assert exc.value.get_codes() == "QC_NCR_NEEDS_ACTION"
    qc.advance_ncr(ncr, tenant_a.owner, action_taken="Blade replaced", status="VERIFIED")
    done = qc.advance_ncr(ncr, tenant_a.owner, status="CLOSED")
    assert done.status == "CLOSED" and done.closed_at


def test_supplier_scorecard_counts_rejections_and_punctuality(tenant_a, method):
    from purchases.models import PurchaseOrder

    prepare(tenant_a, method=method)
    c = tenant_a.company
    product = make_product(c, sku="SC1")
    good, bad = make_supplier(c, name="Good Co"), make_supplier(c, name="Bad Co")
    today = timezone.localdate()
    for sup, rejected, late in ((good, 0, 0), (bad, 20, 5)):
        po = PurchaseOrder.objects.create(
            company=c, supplier=sup, order_date=today - timedelta(days=10), expected_delivery=today - timedelta(days=late + 1),
            created_by=tenant_a.owner, updated_by=tenant_a.owner,
        )
        g, item = grn(tenant_a, sup, product, 100)
        g.purchase_order = po
        g.save(update_fields=["purchase_order"])
        item.quantity_accepted, item.quantity_rejected = D(100 - rejected), D(rejected)
        item.save()
        GoodsReceiptService.complete(g, tenant_a.owner)
        GoodsReceipt.objects.filter(pk=g.pk).update(receipt_date=today - timedelta(days=1))
    card = {r["name"]: r for r in qc.supplier_scorecard(c)}
    assert card["Good Co"]["rejection_pct"] == D("0.0") and card["Good Co"]["on_time_pct"] == D("100.0")
    assert card["Bad Co"]["rejection_pct"] == D("20.0") and card["Bad Co"]["on_time_pct"] == D("0.0")
    assert card["Bad Co"]["avg_lead_days"] == D("9.0")


# --- API ----------------------------------------------------------------------------------------------------

def test_quality_endpoints_are_dark_without_the_flag(tenant_a):
    prepare(tenant_a)
    assert tenant_a.client.get("/api/v1/quality/inspections/").status_code == 404
    quality_on(tenant_a)
    assert tenant_a.client.get("/api/v1/quality/inspections/").status_code == 200


def test_quality_api_roles_and_certificate(tenant_a, method):
    prepare(tenant_a, method=method)
    quality_on(tenant_a)
    c = tenant_a.company
    api = tenant_a.client
    product = make_product(c, sku="API1", track_batch=True)
    tpl = api.post("/api/v1/quality/templates/", {
        "name": "Final check", "product": product.pk, "stage": "FINAL",
        "parameters": [{"name": "Moisture", "kind": "NUMERIC", "min_value": "0", "max_value": "10", "unit": "%"}],
    }, format="json")
    assert tpl.status_code == 201, tpl.data
    bad = api.post("/api/v1/quality/templates/", {"name": "x", "stage": "FINAL", "parameters": [{"name": "n", "kind": "NUMERIC"}]}, format="json")
    assert bad.status_code == 400                           # a number parameter needs a limit
    _u, inv = member(tenant_a, "INVENTORY_STAFF", can_manage_inventory=True)
    assert inv.post("/api/v1/quality/templates/", {"name": "n", "stage": "FINAL"}, format="json").status_code == 403
    _v, viewer = member(tenant_a, "VIEWER")
    assert viewer.get("/api/v1/quality/inspections/").status_code == 200
    assert viewer.post("/api/v1/quality/inspections/", {}, format="json").status_code == 403

    batch = BatchLot.objects.create(company=c, product=product, batch_no="B-API", expiry_date=timezone.localdate() + timedelta(days=60), manufacturing_date=timezone.localdate())
    made = inv.post("/api/v1/quality/inspections/", {"product": product.pk, "qty": "40", "stage": "FINAL", "batch": batch.pk, "source_type": "BATCH"}, format="json")
    assert made.status_code == 201, made.data
    insp = body(made)
    rid = insp["results"][0]["id"]
    assert inv.post(f"/api/v1/quality/inspections/{insp['id']}/record-results/", {"results": {str(rid): "7.5"}}, format="json").status_code == 200
    done = inv.post(f"/api/v1/quality/inspections/{insp['id']}/complete/", {}, format="json")
    assert done.status_code == 200 and body(done)["decision"] == "PASS"
    cert = api.get(f"/api/v1/quality/inspections/{insp['id']}/certificate/")
    assert cert.status_code == 200 and b"Certificate of Analysis" in cert.content and b"Moisture" in cert.content and b"B-API" in cert.content
    # No certificate for a failed inspection.
    fail = inv.post("/api/v1/quality/inspections/", {"product": product.pk, "qty": "1", "stage": "FINAL", "batch": batch.pk, "source_type": "BATCH"}, format="json")
    fid = body(fail)["id"]
    fr = body(fail)["results"][0]["id"]
    inv.post(f"/api/v1/quality/inspections/{fid}/record-results/", {"results": {str(fr): "99"}}, format="json")
    assert inv.post(f"/api/v1/quality/inspections/{fid}/complete/", {}, format="json").status_code == 200
    assert api.get(f"/api/v1/quality/inspections/{fid}/certificate/").status_code == 400
    # Holding and releasing a lot by hand is a manager's decision with a reason.
    assert inv.post(f"/api/v1/quality/batches/{batch.pk}/status/", {"status": "HOLD", "reason": "x"}, format="json").status_code == 403
    assert api.post(f"/api/v1/quality/batches/{batch.pk}/status/", {"status": "HOLD"}, format="json").status_code == 400
    ok = api.post(f"/api/v1/quality/batches/{batch.pk}/status/", {"status": "HOLD", "reason": "Customer complaint"}, format="json")
    assert ok.status_code == 200 and body(ok)["quality_status"] == "HOLD"
    assert api.get("/api/v1/quality/supplier-scorecard/").status_code == 200
    ncr = api.post("/api/v1/quality/non-conformances/", {"product": product.pk, "description": "Cracked pack", "qty": "3"}, format="json")
    assert ncr.status_code == 201 and body(ncr)["number"].startswith("NCR-")
    code = api.post("/api/v1/quality/defect-codes/", {"code": "CRK", "name": "Crack", "severity": "MAJOR"}, format="json")
    assert code.status_code == 201
