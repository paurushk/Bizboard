"""Depth tests (phase 1 of the test plan): the one-step work order every existing company still uses."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.exceptions import BusinessRuleError
from inventory.models import BatchLot, SerialNumber, StockBalance
from inventory.services import InventoryService, SerialNumberService
from manufacturing.models import WorkOrder
from manufacturing.services import complete_work_order, release_work_order
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


def one_step(tenant, method, *, per_unit=2, cost=10, stock=100, fg_kw=None):
    company = prepare(tenant, method=method, separate=False)
    raw = stocked(tenant, "LG-RAW", stock, cost)
    fg = make_product(company, sku="LG-FG", **(fg_kw or {}))
    bom = make_bom(company, fg, [(raw, per_unit)], user=tenant.owner)
    return company, raw, fg, bom


def test_release_takes_the_material_and_complete_adds_the_goods_at_their_cost(tenant_a, method):
    company, raw, fg, bom = one_step(tenant_a, method)
    wo = release_work_order(make_wo(company, bom, 10, user=tenant_a.owner), tenant_a.owner)
    assert wo.status == WorkOrder.Status.RELEASED and wo.issue_mode == "AUTO_AT_RELEASE"
    assert StockBalance.objects.get(company=company, product=raw).on_hand == D(80)
    done = complete_work_order(wo, tenant_a.owner)
    assert done.status == WorkOrder.Status.COMPLETED
    assert StockBalance.objects.get(company=company, product=fg).on_hand == D(10)
    assert InventoryService.available_quantity(company, fg) == D(10)


def test_complete_needs_a_released_order_and_cannot_be_done_twice(tenant_a, method):
    company, raw, fg, bom = one_step(tenant_a, method)
    draft = make_wo(company, bom, 5, user=tenant_a.owner)
    with pytest.raises(BusinessRuleError) as exc:
        complete_work_order(draft, tenant_a.owner)
    assert "released" in str(exc.value).lower()
    wo = release_work_order(draft, tenant_a.owner)
    complete_work_order(wo, tenant_a.owner)
    with pytest.raises(BusinessRuleError):
        complete_work_order(wo, tenant_a.owner)
    with pytest.raises(BusinessRuleError) as exc:
        release_work_order(wo, tenant_a.owner)                                   # not a draft any more
    assert "draft" in str(exc.value).lower()


def test_materials_with_no_cost_cannot_make_finished_goods_appear_from_nowhere(tenant_a, method):
    company, raw, fg, bom = one_step(tenant_a, method, cost=0)
    wo = release_work_order(make_wo(company, bom, 5, user=tenant_a.owner), tenant_a.owner)
    with pytest.raises(BusinessRuleError) as exc:
        complete_work_order(wo, tenant_a.owner)
    assert code(exc) == "MFG_ZERO_COST_COMPLETE"
    assert not StockBalance.objects.filter(company=company, product=fg, on_hand__gt=0).exists()


def test_a_recipe_with_nothing_in_it_cannot_be_released(tenant_a, method):
    company = prepare(tenant_a, method=method, separate=False)
    fg = make_product(company, sku="LG-EMPTY")
    bom = make_bom(company, fg, [], user=tenant_a.owner, status="DRAFT")
    from manufacturing.services import bom as bom_svc

    with pytest.raises(BusinessRuleError) as exc:
        bom_svc.activate_revision(bom, tenant_a.owner)                           # it cannot even become active
    assert code(exc) == "MFG_BOM_EMPTY"
    assert not WorkOrder.objects.filter(company=company).exists()


def test_a_sub_assembly_is_not_exploded_and_must_be_in_stock_to_be_used(tenant_a, method):
    company = prepare(tenant_a, method=method, separate=False)
    sub = make_product(company, sku="LG-SUB", name="Sub-assembly")
    raw = stocked(tenant_a, "LG-SUBRAW", 100, 4)
    make_bom(company, sub, [(raw, 1)], user=tenant_a.owner)                      # the sub-assembly has its own recipe
    fg = make_product(company, sku="LG-TOP")
    top = make_bom(company, fg, [(sub, 2)], user=tenant_a.owner)
    wo = make_wo(company, top, 5, user=tenant_a.owner)
    with pytest.raises(BusinessRuleError) as exc:
        release_work_order(wo, tenant_a.owner)
    assert "sub-assembly" in str(exc.value)
    InventoryService.post_movement(
        company=company, product=sub, movement_type="OPENING_STOCK", quantity=D(50), unit_cost=D(9), user=tenant_a.owner,
    )
    assert release_work_order(wo, tenant_a.owner).status == WorkOrder.Status.RELEASED


def test_a_finished_good_that_tracks_batches_gets_its_batch_with_the_dates(tenant_a, method):
    company, raw, fg, bom = one_step(tenant_a, method, fg_kw={"track_batch": True})
    exp = timezone.localdate() + timedelta(days=180)
    wo = release_work_order(make_wo(company, bom, 4, user=tenant_a.owner, batch_no="LG-B1", exp_date=exp), tenant_a.owner)
    complete_work_order(wo, tenant_a.owner)
    lot = BatchLot.objects.get(company=company, product=fg, batch_no="LG-B1")
    assert lot.expiry_date == exp and lot.manufacturing_date is not None
    assert StockBalance.objects.get(company=company, product=fg, batch=lot).on_hand == D(4)


def test_an_existing_batch_number_with_other_dates_is_refused_and_one_without_dates_is_completed(tenant_a, method):
    company, raw, fg, bom = one_step(tenant_a, method, fg_kw={"track_batch": True})
    exp = timezone.localdate() + timedelta(days=90)
    BatchLot.objects.create(company=company, product=fg, batch_no="CLASH", expiry_date=exp + timedelta(days=30))
    clash = release_work_order(make_wo(company, bom, 2, user=tenant_a.owner, batch_no="CLASH", exp_date=exp), tenant_a.owner)
    with pytest.raises(BusinessRuleError) as exc:
        complete_work_order(clash, tenant_a.owner)
    assert "expiry" in str(exc.value)
    bare = BatchLot.objects.create(company=company, product=fg, batch_no="BARE")
    ok = release_work_order(make_wo(company, bom, 2, user=tenant_a.owner, batch_no="BARE", exp_date=exp), tenant_a.owner)
    complete_work_order(ok, tenant_a.owner)
    bare.refresh_from_db()
    assert bare.expiry_date == exp and bare.manufacturing_date is not None        # the dates were filled in, not argued over


def test_a_finished_good_that_tracks_serials_registers_them(tenant_a, method):
    company, raw, fg, bom = one_step(tenant_a, method, fg_kw={"track_serial": True})
    wo = release_work_order(make_wo(company, bom, 2, user=tenant_a.owner, serial_numbers=["FG-1", "FG-2"]), tenant_a.owner)
    complete_work_order(wo, tenant_a.owner)
    got = dict(SerialNumber.objects.filter(company=company, product=fg).values_list("serial_number", "status"))
    assert got == {"FG-1": "AVAILABLE", "FG-2": "AVAILABLE"}


def test_serials_named_at_release_are_the_ones_taken(tenant_a, method):
    company = prepare(tenant_a, method=method, separate=False)
    comp = make_product(company, sku="LG-SER", track_serial=True, purchase_price="50")
    wh = InventoryService.default_warehouse(company)
    InventoryService.post_movement(
        company=company, product=comp, movement_type="OPENING_STOCK", quantity=D(4), unit_cost=D(50), user=tenant_a.owner,
    )
    SerialNumberService.receive(company=company, product=comp, warehouse=wh, numbers=["C-1", "C-2", "C-3", "C-4"], quantity=D(4), user=tenant_a.owner)
    fg = make_product(company, sku="LG-SER-FG")
    bom = make_bom(company, fg, [(comp, 2)], user=tenant_a.owner)
    wo = release_work_order(make_wo(company, bom, 1, user=tenant_a.owner), tenant_a.owner, component_serials={comp.pk: ["C-2", "C-4"]})
    status = dict(SerialNumber.objects.filter(company=company, product=comp).values_list("serial_number", "status"))
    assert status["C-2"] != "AVAILABLE" and status["C-4"] != "AVAILABLE"
    assert status["C-1"] == "AVAILABLE" and status["C-3"] == "AVAILABLE"
    assert wo.status == WorkOrder.Status.RELEASED


def test_cancelling_a_released_one_step_order_puts_the_material_back(tenant_a, method):
    from manufacturing.services import cancel_work_order

    company, raw, fg, bom = one_step(tenant_a, method)
    wo = release_work_order(make_wo(company, bom, 10, user=tenant_a.owner), tenant_a.owner)
    assert StockBalance.objects.get(company=company, product=raw).on_hand == D(80)
    cancel_work_order(wo, tenant_a.owner)
    assert StockBalance.objects.get(company=company, product=raw).on_hand == D(100)
    wo.refresh_from_db()
    assert wo.status == WorkOrder.Status.CANCELLED
