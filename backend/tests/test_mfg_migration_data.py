"""Phase 3 of the test plan: the manufacturing data migration (0012) run over legacy-shaped rows.

It runs the migration's own functions against the live models after putting rows into the shape a company that
used the old one-step work order would have. The migration is meant to be safe to run twice, so every test that
runs it once also runs it a second time.
"""

import importlib
from decimal import Decimal

import pytest
from django.apps import apps as live_apps
from django.utils import timezone

from inventory.models import MovementType, SerialNumber, TraceLink
from inventory.services import InventoryService
from manufacturing.models import Bom, WorkOrder, WorkOrderLine
from tests.conftest import make_product
from tests.mfg_helpers import make_bom, make_wo, prepare, stocked

pytestmark = pytest.mark.django_db

migration = importlib.import_module("manufacturing.migrations.0012_mfg_phase0_data")


def D(v):
    return Decimal(str(v))


def run_twice():
    migration.forwards(live_apps, None)
    migration.forwards(live_apps, None)         # safe to repeat


def legacy_order(tenant, *, status, qty=10, cost=10):
    """A work order as the one-step flow left it: no number, no product, SEPARATE not yet known, materials issued."""
    company = prepare(tenant, separate=False)
    raw = stocked(tenant, f"MG-RAW-{status}", 1000, cost)
    fg = make_product(company, sku=f"MG-FG-{status}")
    bom = make_bom(company, fg, [(raw, 2)], user=tenant.owner)
    wo = make_wo(company, bom, qty, user=tenant.owner)
    if status in ("RELEASED", "COMPLETED"):
        for line in wo.component_lines.all():
            InventoryService.post_movement(
                company=company, product=line.component, movement_type=MovementType.MANUFACTURE_ISSUE, quantity=line.qty,
                unit_cost=D(cost), user=tenant.owner, reference_type="work_order", reference_id=str(wo.pk),
            )
    WorkOrder.objects.filter(pk=wo.pk).update(
        number="", product=None, issue_mode="SEPARATE", status=status, cost_issued=0, cost_received=0, qty_completed=0,
    )
    WorkOrderLine.objects.filter(work_order=wo).update(qty_issued=0)
    return company, raw, fg, bom, WorkOrder.objects.get(pk=wo.pk)


@pytest.mark.invariant_skip("manufacturing.wip_matches_gl", reason="work orders are built through the ORM as legacy data the ledger never saw")
def test_a_released_order_gets_a_number_a_product_and_its_issued_cost(tenant_a):
    _c, _raw, fg, _bom, wo = legacy_order(tenant_a, status="RELEASED")
    run_twice()
    wo.refresh_from_db()
    assert wo.number == f"WO-{wo.pk}" and wo.product_id == fg.pk
    assert wo.issue_mode == "AUTO_AT_RELEASE"
    assert wo.cost_issued == D("200.00")                                  # 20 units at ₹10
    assert wo.cost_received == 0 and wo.qty_completed == 0               # released, not finished
    assert all(line.qty_issued == line.qty for line in wo.component_lines.all())


def test_a_completed_order_is_marked_fully_received_at_what_was_issued(tenant_a):
    _c, _raw, _fg, _bom, wo = legacy_order(tenant_a, status="COMPLETED")
    run_twice()
    wo.refresh_from_db()
    assert wo.cost_issued == D("200.00") and wo.cost_received == D("200.00")
    assert wo.qty_completed == wo.qty
    assert wo.wip_value == 0                                              # nothing left sitting in progress


def test_a_draft_order_is_numbered_but_claims_no_cost(tenant_a):
    _c, _raw, _fg, _bom, wo = legacy_order(tenant_a, status="DRAFT")
    run_twice()
    wo.refresh_from_db()
    assert wo.number.startswith("WO-") and wo.cost_issued == 0
    assert all(line.qty_issued == 0 for line in wo.component_lines.all())


def test_an_existing_number_is_kept(tenant_a):
    _c, _raw, _fg, _bom, wo = legacy_order(tenant_a, status="DRAFT")
    WorkOrder.objects.filter(pk=wo.pk).update(number="MY-OWN-7")
    run_twice()
    wo.refresh_from_db()
    assert wo.number == "MY-OWN-7"


def test_recipe_revisions_are_numbered_oldest_first_with_the_newest_active_as_default(tenant_a):
    company = prepare(tenant_a)
    fg = make_product(company, sku="MG-REV")
    raw = stocked(tenant_a, "MG-REV-RAW", 10, 5)
    first = make_bom(company, fg, [(raw, 1)], user=tenant_a.owner, name="v1")
    second = make_bom(company, fg, [(raw, 2)], user=tenant_a.owner, name="v2")
    third = make_bom(company, fg, [(raw, 3)], user=tenant_a.owner, name="v3", status="DRAFT")
    # the old data had odd numbers and no default
    for bom, no in ((first, 41), (second, 87), (third, 90)):
        Bom.objects.filter(pk=bom.pk).update(revision_no=no, is_default=False, parent_revision=None)
    run_twice()
    rows = {b.name: b for b in Bom.objects.filter(company=company, product=fg)}
    assert [rows[n].revision_no for n in ("v1", "v2", "v3")] == [1, 2, 3]
    assert rows["v2"].is_default and not rows["v1"].is_default and not rows["v3"].is_default
    assert rows["v2"].parent_revision_id == rows["v1"].pk and rows["v1"].parent_revision_id is None


@pytest.mark.invariant_skip("manufacturing.wip_matches_gl", reason="work orders are built through the ORM as legacy data the ledger never saw")
def test_a_recipe_a_work_order_used_is_locked_and_an_unused_one_is_not(tenant_a):
    _c, _raw, _fg, bom, _wo = legacy_order(tenant_a, status="RELEASED")
    other = make_product(tenant_a.company, sku="MG-UNUSED")
    unused = make_bom(tenant_a.company, other, [(_raw, 1)], user=tenant_a.owner)
    Bom.objects.filter(pk__in=[bom.pk, unused.pk]).update(locked_at=None)
    run_twice()
    bom.refresh_from_db()
    unused.refresh_from_db()
    assert bom.locked_at is not None and unused.locked_at is None


def test_scrapped_serials_of_a_finished_order_become_consumed_once_with_a_trace(tenant_a):
    company, raw, fg, bom, wo = legacy_order(tenant_a, status="COMPLETED")
    comp = make_product(company, sku="MG-SER", track_serial=True)
    line = wo.component_lines.first()
    WorkOrderLine.objects.filter(pk=line.pk).update(component=comp, serial_numbers=["S-1", "S-2"])
    wh = InventoryService.default_warehouse(company)
    for number in ("S-1", "S-2", "S-3"):
        SerialNumber.objects.create(company=company, product=comp, warehouse=wh, serial_number=number, status="SCRAPPED")
    run_twice()
    status = dict(SerialNumber.objects.filter(company=company, product=comp).values_list("serial_number", "status"))
    assert status == {"S-1": "CONSUMED", "S-2": "CONSUMED", "S-3": "SCRAPPED"}       # S-3 is not proven to be ours
    assert TraceLink.objects.filter(company=company, work_order_id=wo.pk, document_type="work_order").count() == 2


def test_serials_of_a_draft_order_or_in_another_state_are_left_alone(tenant_a):
    company, raw, fg, bom, wo = legacy_order(tenant_a, status="DRAFT")
    comp = make_product(company, sku="MG-SER2", track_serial=True)
    line = wo.component_lines.first()
    WorkOrderLine.objects.filter(pk=line.pk).update(component=comp, serial_numbers=["D-1"])
    wh = InventoryService.default_warehouse(company)
    SerialNumber.objects.create(company=company, product=comp, warehouse=wh, serial_number="D-1", status="SCRAPPED")
    run_twice()
    assert SerialNumber.objects.get(company=company, serial_number="D-1").status == "SCRAPPED"
    assert TraceLink.objects.filter(company=company, work_order_id=wo.pk).count() == 0


@pytest.mark.invariant_skip("manufacturing.consumed_serial_has_trace", reason="work orders are built through the ORM as legacy data the ledger never saw")
def test_going_backwards_returns_only_the_serials_the_migration_converted(tenant_a):
    company, raw, fg, bom, wo = legacy_order(tenant_a, status="COMPLETED")
    comp = make_product(company, sku="MG-SER3", track_serial=True)
    line = wo.component_lines.first()
    WorkOrderLine.objects.filter(pk=line.pk).update(component=comp, serial_numbers=["B-1"])
    wh = InventoryService.default_warehouse(company)
    SerialNumber.objects.create(company=company, product=comp, warehouse=wh, serial_number="B-1", status="SCRAPPED")
    SerialNumber.objects.create(company=company, product=comp, warehouse=wh, serial_number="B-2", status="CONSUMED")
    migration.forwards(live_apps, None)
    assert SerialNumber.objects.get(company=company, serial_number="B-1").status == "CONSUMED"
    migration.backwards(live_apps, None)
    assert SerialNumber.objects.get(company=company, serial_number="B-1").status == "SCRAPPED"
    assert SerialNumber.objects.get(company=company, serial_number="B-2").status == "CONSUMED"    # not ours to touch


@pytest.mark.invariant_skip("manufacturing.wip_matches_gl", reason="work orders are built through the ORM as legacy data the ledger never saw")
def test_every_company_is_handled_and_none_bleeds_into_another(tenant_a, tenant_b):
    _ca, _ra, _fa, _ba, wo_a = legacy_order(tenant_a, status="COMPLETED")
    _cb, _rb, _fb, _bb, wo_b = legacy_order(tenant_b, status="RELEASED", cost=7)
    run_twice()
    wo_a.refresh_from_db()
    wo_b.refresh_from_db()
    assert wo_a.cost_issued == D("200.00") and wo_b.cost_issued == D("140.00")
    assert wo_a.company_id != wo_b.company_id and timezone.now()
