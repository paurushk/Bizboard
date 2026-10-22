"""Depth tests (phase 1 of the test plan): lot allocation, genealogy helpers, the other attention rows."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.utils import timezone

from core.exceptions import BusinessRuleError
from inventory.models import BatchLot, MovementType, TraceLink
from inventory.services import InventoryService
from insights.attention import build_attention_rows
from manufacturing.services import allocation, trace
from tests.conftest import make_product
from tests.mfg_helpers import make_bom, make_wo, prepare, stocked

pytestmark = pytest.mark.django_db


def D(v):
    return Decimal(str(v))


def lot_with_stock(company, user, product, batch_no, qty, expiry_days, cost=10):
    lot = BatchLot.objects.create(
        company=company, product=product, batch_no=batch_no, expiry_date=timezone.localdate() + timedelta(days=expiry_days),
    )
    InventoryService.post_movement(
        company=company, product=product, batch=lot, movement_type=MovementType.PURCHASE, quantity=D(qty),
        unit_cost=D(cost), user=user, reference_type="test", reference_id=batch_no,
    )
    return lot


def code(exc):
    return exc.value.get_codes()


# --- which lots an issue draws from ---------------------------------------------------------------------------------

@pytest.fixture
def batched(tenant_a):
    company = prepare(tenant_a)
    comp = make_product(company, sku="AL-C", name="Batched flour", track_batch=True)
    early = lot_with_stock(company, tenant_a.owner, comp, "EARLY", 30, 10)
    late = lot_with_stock(company, tenant_a.owner, comp, "LATE", 50, 90)
    return company, comp, early, late, InventoryService.default_warehouse(company)


def test_an_item_that_does_not_track_batches_is_one_unbatched_take(tenant_a):
    company = prepare(tenant_a)
    plain = stocked(tenant_a, "AL-PLAIN", 100, 5)
    assert allocation.allocate_batches(company, InventoryService.default_warehouse(company), plain, 40) == [(None, D(40))]


def test_first_expiry_first_out_spans_lots(batched):
    company, comp, early, late, wh = batched
    assert allocation.allocate_batches(company, wh, comp, 20) == [(early, D(20))]
    got = allocation.allocate_batches(company, wh, comp, 60)
    assert [(b.batch_no, q) for b, q in got] == [("EARLY", D(30)), ("LATE", D(30))]


def test_not_enough_batched_stock_is_refused_with_the_shortfall(batched):
    company, comp, early, late, wh = batched
    with pytest.raises(BusinessRuleError) as exc:
        allocation.allocate_batches(company, wh, comp, 100)
    assert code(exc) == "MFG_SHORT_STOCK" and "short 20" in str(exc.value)


def test_an_item_with_no_stock_at_all_says_no_batch_is_available(tenant_a):
    company = prepare(tenant_a)
    comp = make_product(company, sku="AL-NONE", track_batch=True)
    with pytest.raises(BusinessRuleError) as exc:
        allocation.allocate_batches(company, InventoryService.default_warehouse(company), comp, 5)
    assert code(exc) == "MFG_SHORT_STOCK"


def test_a_named_batch_is_used_and_refused_when_it_is_short(batched):
    company, comp, early, late, wh = batched
    assert allocation.allocate_batches(company, wh, comp, 10, batch=late) == [(late, D(10))]
    with pytest.raises(BusinessRuleError) as exc:
        allocation.allocate_batches(company, wh, comp, 40, batch=early)
    assert code(exc) == "MFG_SHORT_STOCK" and "EARLY" in str(exc.value)


def test_explicit_lot_allocations_must_add_up_and_belong_to_the_item(batched, tenant_a):
    company, comp, early, late, wh = batched
    ok = allocation.allocate_batches(
        company, wh, comp, 25, lot_allocations=[{"batch_id": late.pk, "qty": 20}, {"batch_id": early.pk, "qty": 5}],
    )
    assert [(b.batch_no, q) for b, q in ok] == [("LATE", D(20)), ("EARLY", D(5))]
    for bad in (
        [{"batch_id": late.pk, "qty": 10}],                                     # adds up to less
        [{"batch_id": late.pk, "qty": 30}],                                     # adds up to more
    ):
        with pytest.raises(BusinessRuleError) as exc:
            allocation.allocate_batches(company, wh, comp, 25, lot_allocations=bad)
        assert code(exc) == "MFG_BAD_LOT_ALLOCATION"
    other = make_product(company, sku="AL-OTHER", track_batch=True)
    foreign = BatchLot.objects.create(company=company, product=other, batch_no="NOT-MINE")
    with pytest.raises(BusinessRuleError) as exc:
        allocation.allocate_batches(company, wh, comp, 5, lot_allocations=[{"batch_id": foreign.pk, "qty": 5}])
    assert code(exc) == "MFG_BAD_LOT_ALLOCATION"


def test_empty_allocation_rows_fall_back_to_first_expiry_first_out(batched):
    company, comp, early, late, wh = batched
    got = allocation.allocate_batches(company, wh, comp, 5, lot_allocations=[{"batch_id": None, "qty": 0}])
    assert got == [(early, D(5))]


# --- genealogy ------------------------------------------------------------------------------------------------------

def links(tenant, **kw):
    company = tenant.company
    prod = make_product(company, sku=f"TR-{TraceLink.objects.count()}")
    return TraceLink.objects.create(company=company, work_order_id=kw.pop("wo", 1), input_product=prod, qty=D(1), **kw), prod


def test_serials_released_by_a_return_leave_the_trace_and_come_back_when_the_return_is_reversed(tenant_a):
    company = prepare(tenant_a)
    prod = make_product(company, sku="TR-S", track_serial=True)
    wo = type("W", (), {"company_id": company.pk, "pk": 9})()
    for number in ("S1", "S2", "S3"):
        TraceLink.objects.create(company=company, work_order_id=9, input_product=prod, input_serial=number, qty=D(1))
    assert trace.release_serials(wo, prod, ["S1", " S2 ", ""]) == 2
    assert TraceLink.objects.filter(company=company, reversed_at__isnull=True).count() == 1
    assert trace.release_serials(wo, prod, []) == 0 and trace.release_serials(wo, prod, None) == 0
    assert trace.restore_serials(wo, prod, ["S1"]) == 1
    assert TraceLink.objects.filter(company=company, reversed_at__isnull=True).count() == 2
    assert trace.restore_serials(wo, prod, []) == 0


def test_a_whole_work_order_can_be_dropped_from_the_trace(tenant_a):
    company = prepare(tenant_a)
    prod = make_product(company, sku="TR-W")
    for _ in range(3):
        TraceLink.objects.create(company=company, work_order_id=5, input_product=prod, qty=D(1))
    TraceLink.objects.create(company=company, work_order_id=6, input_product=prod, qty=D(1))
    wo = type("W", (), {"company_id": company.pk, "pk": 5})()
    assert trace.reverse_work_order(wo) == 3
    assert TraceLink.objects.filter(company=company, reversed_at__isnull=True).count() == 1


def test_output_serials_are_paired_with_the_open_links(tenant_a):
    company = prepare(tenant_a)
    prod = make_product(company, sku="TR-O", track_serial=True)
    TraceLink.objects.create(company=company, work_order_id=7, input_product=prod, qty=D(1))
    wo = type("W", (), {"company_id": company.pk, "pk": 7, "product": prod})()
    trace.link_outputs(wo, serials=["OUT-1"])
    assert TraceLink.objects.get(company=company, work_order_id=7).output_serial == "OUT-1"
    TraceLink.objects.create(company=company, work_order_id=8, input_product=prod, qty=D(1))
    wo8 = type("W", (), {"company_id": company.pk, "pk": 8, "product": prod})()
    trace.link_outputs(wo8, serials=["A", "B"])                       # several: the pairing stays at lot level
    assert TraceLink.objects.get(company=company, work_order_id=8).output_serial == ""


def test_trace_forward_names_the_customer_document_even_when_it_cannot_be_read(tenant_a):
    company = prepare(tenant_a)
    prod = make_product(company, sku="TR-F", track_batch=True)
    lot = lot_with_stock(company, tenant_a.owner, prod, "FWD-1", 20, 60)
    InventoryService.post_movement(
        company=company, product=prod, batch=lot, movement_type=MovementType.SALE, quantity=D(5), user=tenant_a.owner,
        reference_type="sales_invoice", reference_id="999999",
    )
    InventoryService.post_movement(
        company=company, product=prod, batch=lot, movement_type=MovementType.SALE, quantity=D(2), user=tenant_a.owner,
        reference_type="delivery_challan", reference_id="999999",
    )
    out = trace.trace_forward(company, lot)
    assert out["made_from_it"] == []
    assert sorted(c["document"] for c in out["sent_to"]) == ["delivery_challan", "sales_invoice"]
    assert all("customer" not in c for c in out["sent_to"])           # the missing document must not break the recall


def test_trace_back_names_where_a_received_lot_came_from(tenant_a):
    company = prepare(tenant_a)
    prod = make_product(company, sku="TR-B", track_batch=True)
    fg = make_product(company, sku="TR-B-FG", track_batch=True)
    raw = lot_with_stock(company, tenant_a.owner, prod, "RAW-9", 10, 60)
    out_lot = BatchLot.objects.create(company=company, product=fg, batch_no="FG-9")
    TraceLink.objects.create(
        company=company, work_order_id=1, input_product=prod, input_batch=raw, output_batch=out_lot, output_product=fg, qty=D(4),
    )
    rows = trace.trace_back(company, out_lot)
    assert rows[0]["batch"] == "RAW-9" and rows[0]["source"]["reference_type"] == "test"
    assert trace._source_of(company, out_lot) is None                 # a made lot has no supplier document


# --- the other attention rows ---------------------------------------------------------------------------------------

def rows_for(company, code_, as_of=None):
    cache.clear()
    return [r for r in build_attention_rows(company, None, as_of=as_of) if r["code"] == code_]


def enable(tenant, *names):
    flags = dict(tenant.company.feature_flags or {})
    flags.update({n: True for n in names})
    tenant.company.feature_flags = flags
    tenant.company.save(update_fields=["feature_flags"])


def test_a_lot_on_hold_for_over_a_week_and_an_overdue_quality_problem_raise_rows(tenant_a):
    from quality.models import NonConformance

    company = prepare(tenant_a)
    enable(tenant_a, "MFG_QUALITY")
    prod = make_product(company, sku="AT-Q", track_batch=True)
    lot = lot_with_stock(company, tenant_a.owner, prod, "HOLD-OLD", 5, 60)
    fresh = lot_with_stock(company, tenant_a.owner, prod, "HOLD-NEW", 5, 60)
    BatchLot.objects.filter(pk=lot.pk).update(quality_status="HOLD", updated_at=timezone.now() - timedelta(days=9))
    BatchLot.objects.filter(pk=fresh.pk).update(quality_status="HOLD")
    ncr = NonConformance.objects.create(
        company=company, number="NCR-1", source_type="INTERNAL", product=prod, qty=D(1), description="Cracked",
        status="OPEN", due_date=timezone.localdate() - timedelta(days=3),
    )
    held = rows_for(company, "BATCH_ON_HOLD")
    assert [r["dedupe_key"] for r in held] == [f"BATCH_ON_HOLD:{lot.pk}"]               # the fresh hold is not nagged yet
    late = rows_for(company, "NCR_OVERDUE")
    assert [r["dedupe_key"] for r in late] == [f"NCR_OVERDUE:{ncr.pk}"]
    NonConformance.objects.filter(pk=ncr.pk).update(status="CLOSED")
    assert rows_for(company, "NCR_OVERDUE") == []


def test_a_work_order_long_in_progress_with_cost_tied_up_raises_a_row(tenant_a):
    from manufacturing.models import WorkOrder
    from manufacturing.services import issue as issue_svc
    from manufacturing.services import release_work_order

    company = prepare(tenant_a, separate=True)
    raw = stocked(tenant_a, "AT-W", 100, 10)
    fg = make_product(company, sku="AT-W-FG")
    bom = make_bom(company, fg, [(raw, 1)], user=tenant_a.owner)
    wo = release_work_order(make_wo(company, bom, 10, user=tenant_a.owner), tenant_a.owner)
    issue_svc.post_issue(issue_svc.create_issue(wo, tenant_a.owner), tenant_a.owner)
    assert rows_for(company, "WIP_STALE") == []                                          # released today: not stale
    WorkOrder.objects.filter(pk=wo.pk).update(released_at=timezone.localdate() - timedelta(days=45))
    row = rows_for(company, "WIP_STALE")[0]
    assert row["dedupe_key"] == f"WIP_STALE:{wo.pk}" and row["money_impact_paise"] == 10000
    assert row["params"]["days"] >= 45


def test_goods_late_back_from_a_job_worker_and_an_itc04_not_filed_raise_rows(tenant_a):
    from jobwork.models import JobWorkChallan
    from jobwork.services import out
    from tests.conftest import make_supplier

    company = prepare(tenant_a)
    enable(tenant_a, "MFG_JOB_WORK")
    raw = stocked(tenant_a, "AT-JW", 100, 10)
    order = out.create_order(company, tenant_a.owner, supplier=make_supplier(company, name="Slow Worker"))
    challan = out.issue_challan(out.create_challan(order, tenant_a.owner, [{"product": raw, "qty": 10}]), tenant_a.owner)
    old = timezone.localdate() - timedelta(days=400)
    JobWorkChallan.objects.filter(pk=challan.pk).update(challan_date=old)
    late = rows_for(company, "JOBWORK_AGEING")
    assert len(late) == 1 and late[0]["severity"] == "critical" and late[0]["params"]["variant"] == "overdue"
    assert late[0]["money_impact_paise"] == 10000          # 10 units at ₹10
    itc = rows_for(company, "ITC04_DUE", as_of=timezone.localdate())
    assert all(r["dedupe_key"].startswith("ITC04_DUE:") for r in itc)
