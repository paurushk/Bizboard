"""Depth tests (phase 1 of the test plan), third batch: what the issue, return and receipt documents refuse, the date
rules, and the helpers every posting leans on."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.invariants import assert_all_invariants
from inventory.models import BatchLot, SerialNumber, StockBalance
from inventory.services import InventoryService, SerialNumberService
from manufacturing.models import MaterialIssue, WorkOrder
from manufacturing.services import flow, quick_entry, release_work_order
from manufacturing.services import issue as issue_svc
from manufacturing.services import receipt as receipt_svc
from manufacturing.services.common import assert_doc_date, get_settings, qty3, required_qty, unit_factor
from tests.conftest import make_product
from tests.mfg_helpers import make_bom, make_wo, prepare, stocked

pytestmark = pytest.mark.django_db


def D(v):
    return Decimal(str(v))


@pytest.fixture(params=["WAVG", "FIFO"])
def method(request):
    return request.param


def code(exc):
    return exc.value.get_codes()


def world(tenant, method, *, qty=10, per_unit=2, stock=200, cost=10, fg_kw=None):
    company = prepare(tenant, method=method, separate=True)
    raw = stocked(tenant, "DD-RAW", stock, cost)
    fg = make_product(company, sku="DD-FG", **(fg_kw or {}))
    bom = make_bom(company, fg, [(raw, per_unit)], user=tenant.owner)
    wo = release_work_order(make_wo(company, bom, qty, user=tenant.owner), tenant.owner)
    return company, raw, fg, bom, wo


# --- drafts the rules refuse ------------------------------------------------------------------------------------------

def test_an_issue_line_must_name_a_material_of_this_order_with_a_quantity(tenant_a, method):
    company, raw, fg, bom, wo = world(tenant_a, method)
    other = make_product(company, sku="DD-OTHER")
    other_wo = release_work_order(make_wo(company, make_bom(company, other, [(raw, 1)], user=tenant_a.owner), 5, user=tenant_a.owner), tenant_a.owner)
    foreign_line = other_wo.component_lines.first()
    for lines, expect in (
        ([{"wo_line": foreign_line.pk, "qty": 1}], "MFG_BAD_WO_LINE"),                           # another order's line
        ([{"qty": 1}], "MFG_LINE_NEEDS_COMPONENT"),                                              # no material at all
        ([{"wo_line": wo.component_lines.first(), "qty": 0}], "MFG_BAD_QTY"),
        ([{"wo_line": wo.component_lines.first(), "qty": -2}], "MFG_BAD_QTY"),
    ):
        with pytest.raises(BusinessRuleError) as exc:
            issue_svc.create_issue(wo, tenant_a.owner, lines)
        assert code(exc) == expect, lines
    assert not MaterialIssue.objects.filter(work_order=wo).exists()                              # nothing half-made


def test_a_material_can_be_named_by_the_item_instead_of_the_line(tenant_a, method):
    company, raw, fg, bom, wo = world(tenant_a, method)
    doc = issue_svc.create_issue(wo, tenant_a.owner, [{"component": raw, "qty": 5}])
    assert doc.lines.get().wo_line_id == wo.component_lines.first().pk
    assert issue_svc.post_issue(doc, tenant_a.owner).status == "POSTED"


def test_nothing_left_to_issue_is_said_plainly(tenant_a, method):
    company, raw, fg, bom, wo = world(tenant_a, method)
    issue_svc.post_issue(issue_svc.create_issue(wo, tenant_a.owner), tenant_a.owner)             # everything
    with pytest.raises(BusinessRuleError) as exc:
        issue_svc.create_issue(wo, tenant_a.owner)
    assert code(exc) == "MFG_NOTHING_TO_ISSUE"


def test_an_order_that_is_not_running_takes_no_documents(tenant_a, method):
    company, raw, fg, bom, wo = world(tenant_a, method)
    flow.cancel_separate(wo, tenant_a.owner)
    for call in (lambda: issue_svc.create_issue(wo, tenant_a.owner), lambda: receipt_svc.create_receipt(wo, tenant_a.owner)):
        with pytest.raises(BusinessRuleError) as exc:
            call()
        assert code(exc) == "MFG_BAD_WO_STATUS"


def test_a_serial_tracked_material_needs_its_serial_numbers_to_be_issued(tenant_a, method):
    company = prepare(tenant_a, method=method, separate=True)
    comp = make_product(company, sku="DD-SER", track_serial=True, purchase_price="30")
    wh = InventoryService.default_warehouse(company)
    InventoryService.post_movement(company=company, product=comp, movement_type="OPENING_STOCK", quantity=D(3), unit_cost=D(30), user=tenant_a.owner)
    SerialNumberService.receive(company=company, product=comp, warehouse=wh, numbers=["X1", "X2", "X3"], quantity=D(3), user=tenant_a.owner)
    fg = make_product(company, sku="DD-SER-FG")
    bom = make_bom(company, fg, [(comp, 1)], user=tenant_a.owner)
    wo = release_work_order(make_wo(company, bom, 2, user=tenant_a.owner), tenant_a.owner)
    with pytest.raises(BusinessRuleError) as exc:
        issue_svc.post_issue(issue_svc.create_issue(wo, tenant_a.owner), tenant_a.owner)
    assert code(exc) == "MFG_SERIALS_REQUIRED"
    line = wo.component_lines.first()
    issue_svc.post_issue(issue_svc.create_issue(wo, tenant_a.owner, [{"wo_line": line, "qty": 2, "serial_numbers": ["X1", "X3"]}]), tenant_a.owner)
    got = dict(SerialNumber.objects.filter(company=company, product=comp).values_list("serial_number", "status"))
    assert got == {"X1": "CONSUMED", "X2": "AVAILABLE", "X3": "CONSUMED"}
    assert_all_invariants(company)


# --- approval refusals ---------------------------------------------------------------------------------------------

def test_the_approval_steps_refuse_what_does_not_make_sense(tenant_a, method):
    company, raw, fg, bom, wo = world(tenant_a, method)
    line = wo.component_lines.first()
    within_plan = issue_svc.create_issue(wo, tenant_a.owner, [{"wo_line": line, "qty": 5}])
    with pytest.raises(BusinessRuleError) as exc:
        issue_svc.request_approval(within_plan, tenant_a.owner)
    assert code(exc) == "MFG_APPROVAL_NOT_NEEDED"
    over = issue_svc.create_issue(wo, tenant_a.owner, [{"wo_line": line, "qty": 80}])           # 20 needed; no reason given
    over.lines.update(extra_reason="")
    with pytest.raises(BusinessRuleError) as exc:
        issue_svc.request_approval(over, tenant_a.owner)
    assert code(exc) == "MFG_EXTRA_NEEDS_REASON"
    with pytest.raises(BusinessRuleError) as exc:
        issue_svc.decide_approval(over, tenant_a.owner, approve=True)                          # nobody has asked
    assert code(exc) == "MFG_APPROVAL_NONE"
    posted = issue_svc.post_issue(within_plan, tenant_a.owner)
    with pytest.raises(BusinessRuleError) as exc:
        issue_svc.request_approval(posted, tenant_a.owner)
    assert code(exc) == "MFG_DOC_NOT_DRAFT"


def test_a_manager_posting_a_draft_that_was_asked_about_counts_as_the_approval(tenant_a, method):
    company, raw, fg, bom, wo = world(tenant_a, method)
    line = wo.component_lines.first()
    draft = issue_svc.create_issue(wo, tenant_a.owner, [{"wo_line": line, "qty": 40, "extra_reason": "spill"}])
    issue_svc.request_approval(draft, tenant_a.owner, "please")
    issue_svc.post_issue(draft, tenant_a.owner, is_manager=True)
    draft.refresh_from_db()
    assert draft.status == "POSTED" and draft.approval == "APPROVED" and draft.approval_decided_by_id == tenant_a.owner.pk


# --- returns and receipts --------------------------------------------------------------------------------------------

def test_a_return_must_name_a_line_and_cannot_be_more_than_is_out(tenant_a, method):
    company, raw, fg, bom, wo = world(tenant_a, method)
    line = wo.component_lines.first()
    issue_svc.post_issue(issue_svc.create_issue(wo, tenant_a.owner, [{"wo_line": line, "qty": 8}]), tenant_a.owner)
    with pytest.raises(BusinessRuleError) as exc:
        issue_svc.create_return(wo, tenant_a.owner, [])
    assert code(exc) == "MFG_EMPTY_DOC"
    with pytest.raises(BusinessRuleError) as exc:
        issue_svc.create_return(wo, tenant_a.owner, [{"qty": 1}])
    assert code(exc) == "MFG_LINE_NEEDS_COMPONENT"
    with pytest.raises(BusinessRuleError) as exc:
        issue_svc.create_return(wo, tenant_a.owner, [{"wo_line": line, "qty": 0}])
    assert code(exc) == "MFG_BAD_QTY"
    too_much = issue_svc.create_return(wo, tenant_a.owner, [{"wo_line": line, "qty": 9}])
    with pytest.raises(BusinessRuleError) as exc:
        issue_svc.post_return(too_much, tenant_a.owner)
    assert code(exc) == "MFG_OVER_RETURN"


def test_a_receipt_needs_a_quantity_and_cannot_overrun_the_plan(tenant_a, method):
    company, raw, fg, bom, wo = world(tenant_a, method)
    issue_svc.post_issue(issue_svc.create_issue(wo, tenant_a.owner), tenant_a.owner)
    empty = receipt_svc.create_receipt(wo, tenant_a.owner, {"lines": [{"kind": "MAIN", "qty_good": 0}]})
    with pytest.raises(BusinessRuleError) as exc:
        receipt_svc.post_receipt(empty, tenant_a.owner)
    assert code(exc) == "MFG_BAD_QTY"
    cfg = get_settings(company)
    cfg.over_receipt_pct = D(0)
    cfg.save()
    over = receipt_svc.create_receipt(wo, tenant_a.owner, {"lines": [{"kind": "MAIN", "qty_good": 11}]})
    with pytest.raises(BusinessRuleError) as exc:
        receipt_svc.post_receipt(over, tenant_a.owner)
    assert code(exc) == "MFG_OVER_RECEIPT"
    cfg.over_receipt_pct = D(10)
    cfg.save()
    assert receipt_svc.post_receipt(over, tenant_a.owner).status == "POSTED"                 # 10 % over the plan is allowed


def test_a_receipt_line_for_another_item_as_the_main_output_is_refused(tenant_a, method):
    company, raw, fg, bom, wo = world(tenant_a, method)
    issue_svc.post_issue(issue_svc.create_issue(wo, tenant_a.owner), tenant_a.owner)
    other = make_product(company, sku="DD-NOT-MAIN")
    with pytest.raises(BusinessRuleError) as exc:
        receipt_svc.create_receipt(wo, tenant_a.owner, {"lines": [{"kind": "MAIN", "product": other, "qty_good": 5}]})
    assert code(exc) == "MFG_BAD_OUTPUT"
    with pytest.raises(BusinessRuleError) as exc:
        receipt_svc.create_receipt(wo, tenant_a.owner, {"lines": [{"kind": "BY_PRODUCT", "qty_good": 1}]})
    assert code(exc) == "MFG_LINE_NEEDS_COMPONENT"


def test_an_existing_output_batch_must_agree_on_its_dates_and_gets_the_missing_ones(tenant_a, method):
    company, raw, fg, bom, wo = world(tenant_a, method, fg_kw={"track_batch": True})
    issue_svc.post_issue(issue_svc.create_issue(wo, tenant_a.owner), tenant_a.owner)
    exp = timezone.localdate() + timedelta(days=60)
    BatchLot.objects.create(company=company, product=fg, batch_no="DD-CLASH", expiry_date=exp + timedelta(days=10))
    BatchLot.objects.create(company=company, product=fg, batch_no="DD-MFG", manufacturing_date=timezone.localdate() - timedelta(days=9))
    BatchLot.objects.create(company=company, product=fg, batch_no="DD-BARE")
    clash = receipt_svc.create_receipt(wo, tenant_a.owner, {"batch_no": "DD-CLASH", "exp_date": exp, "lines": [{"kind": "MAIN", "qty_good": 2}]})
    with pytest.raises(BusinessRuleError) as exc:
        receipt_svc.post_receipt(clash, tenant_a.owner)
    assert code(exc) == "MFG_BATCH_MISMATCH"
    mfg_clash = receipt_svc.create_receipt(wo, tenant_a.owner, {"batch_no": "DD-MFG", "mfg_date": timezone.localdate(), "lines": [{"kind": "MAIN", "qty_good": 2}]})
    with pytest.raises(BusinessRuleError) as exc:
        receipt_svc.post_receipt(mfg_clash, tenant_a.owner)
    assert code(exc) == "MFG_BATCH_MISMATCH"
    bare = receipt_svc.create_receipt(wo, tenant_a.owner, {"batch_no": "DD-BARE", "exp_date": exp, "mfg_date": timezone.localdate(), "lines": [{"kind": "MAIN", "qty_good": 2}]})
    receipt_svc.post_receipt(bare, tenant_a.owner)
    lot = BatchLot.objects.get(company=company, batch_no="DD-BARE")
    assert lot.expiry_date == exp and lot.manufacturing_date == timezone.localdate()


def test_output_that_has_been_sold_cannot_be_taken_back_out(tenant_a, method):
    company, raw, fg, bom, wo = world(tenant_a, method)
    issue_svc.post_issue(issue_svc.create_issue(wo, tenant_a.owner), tenant_a.owner)
    rec = receipt_svc.post_receipt(receipt_svc.create_receipt(wo, tenant_a.owner, {"is_final": True}), tenant_a.owner)
    InventoryService.post_movement(
        company=company, product=fg, movement_type="SALE", quantity=D(4), user=tenant_a.owner, reference_type="test", reference_id="1",
    )
    with pytest.raises(BusinessRuleError) as exc:
        receipt_svc.reverse_receipt(rec, tenant_a.owner, "oops")
    assert code(exc) == "MFG_REVERSAL_ORDER" and "sold or used" in str(exc.value)
    assert StockBalance.objects.get(company=company, product=fg).on_hand == D(6)


# --- dates ----------------------------------------------------------------------------------------------------------------

def test_a_future_date_is_refused_and_an_old_one_needs_a_manager(tenant_a):
    company = prepare(tenant_a)
    today = timezone.localdate()
    with pytest.raises(BusinessRuleError) as exc:
        assert_doc_date(company, today + timedelta(days=1))
    assert code(exc) == "MFG_FUTURE_DATE"
    cfg = get_settings(company)
    cfg.backdate_days = 7
    cfg.save()
    old = today - timedelta(days=30)
    with pytest.raises(BusinessRuleError) as exc:
        assert_doc_date(company, old, can_backdate=False)
    assert code(exc) == "MFG_BACKDATE_NEEDS_MANAGER"
    assert assert_doc_date(company, old, can_backdate=True) == old
    assert assert_doc_date(company, str(today - timedelta(days=3)) + "T10:00:00", can_backdate=False) == today - timedelta(days=3)
    assert assert_doc_date(company, None) == today


# --- helpers --------------------------------------------------------------------------------------------------------------

def test_the_quantity_a_recipe_needs_allows_for_scrap_yield_and_unit(tenant_a):
    assert required_qty(2, 1, 10) == D("20.000")
    assert required_qty(2, 10, 10) == D("2.000")                                          # the recipe is for a batch of ten
    assert required_qty(10, 1, 1, scrap_pct=5) == D("10.500")
    assert required_qty(10, 1, 1, yield_pct=80) == D("12.500")
    assert required_qty(10, 1, 1, factor=D("0.5")) == D("5.000")
    for bad in ({"bom_output_qty": 0}, {"yield_pct": -5}):
        with pytest.raises(BusinessRuleError):
            required_qty(1, bad.get("bom_output_qty", 1), 1, yield_pct=bad.get("yield_pct", 100))
    assert qty3("1.23456") == D("1.235")


def test_an_alternate_unit_converts_by_the_products_rate(tenant_a):
    from masters.models import Unit

    company = prepare(tenant_a)
    box = Unit.objects.create(company=company, name="Box", short_name="bx") if hasattr(Unit, "company") else Unit.objects.create(name="Box", short_name="bx")
    product = make_product(company, sku="DD-UNIT")
    assert unit_factor(product, None) == 1 and unit_factor(product, box) == 1             # not its alternate: no conversion
    product.alternate_unit_id = box.pk
    product.conversion_rate = D(12)
    assert unit_factor(product, box) == D(12)
    product.conversion_rate = D(0)
    with pytest.raises(BusinessRuleError):
        unit_factor(product, box)


# --- quick production ----------------------------------------------------------------------------------------------------

def test_quick_production_refuses_a_material_that_is_not_in_the_recipe_and_an_empty_run(tenant_a, method):
    company = prepare(tenant_a, method=method, separate=True)
    raw = stocked(tenant_a, "QP-RAW", 100, 10)
    stray = stocked(tenant_a, "QP-STRAY", 100, 10)
    fg = make_product(company, sku="QP-FG")
    make_bom(company, fg, [(raw, 1)], user=tenant_a.owner)
    with pytest.raises(BusinessRuleError) as exc:
        quick_entry.quick_production(company, tenant_a.owner, product=fg, qty=5, components={stray.pk: 3})
    assert code(exc) == "MFG_BAD_WO_LINE"
    assert not WorkOrder.objects.filter(company=company).exists()                        # all or nothing


def test_quick_production_takes_what_was_actually_used_and_marks_extra_use(tenant_a, method):
    company = prepare(tenant_a, method=method, separate=True)
    raw = stocked(tenant_a, "QP2-RAW", 100, 10)
    fg = make_product(company, sku="QP2-FG")
    make_bom(company, fg, [(raw, 1)], user=tenant_a.owner)
    wo = quick_entry.quick_production(company, tenant_a.owner, product=fg, qty=10, components={raw.pk: 12})
    line = wo.issues.first().lines.get()
    assert line.qty == D(12) and line.is_extra and line.extra_reason == "Entered in quick production"
    assert StockBalance.objects.get(company=company, product=raw).on_hand == D(88)
    assert_all_invariants(company)
