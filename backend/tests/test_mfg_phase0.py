"""Manufacturing phase 0: roles, BOM revisions, line maths, the three defect fixes, costing foundations."""

import re
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from core.exceptions import BusinessRuleError
from inventory.models import (
    MovementType, SerialNumber, StockBalance, StockMovement, TraceLink, Warehouse,
)
from inventory.services import InventoryService
from manufacturing.models import Bom
from manufacturing.services import (
    bom as bom_svc, cancel_work_order, complete_work_order, release_work_order,
)
from manufacturing.services.common import cost_receipt, required_qty
from tests.conftest import add_stock, make_product
from tests.mfg_helpers import account_net, body, make_bom, make_wo, member, prepare, rows, stocked

pytestmark = pytest.mark.django_db


# --- pure maths -------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "line_qty,out_qty,wo_qty,scrap,factor,yld,expected",
    [
        ("2", "1", "10", 0, 1, 100, "20.000"),                 # plain per-unit BOM
        ("62", "100", "250", 0, 1, 100, "155.000"),            # 100 kg batch recipe, 250 kg order
        ("62", "100", "250", 2, 1, 100, "158.100"),            # 2 % line scrap
        ("1", "1", "100", 0, 1, 98, "102.041"),                # 98 % yield: 100 good units need more in
        ("500", "1", "3", 0, Decimal("0.001"), 100, "1.500"),  # grams on the line, kg in stock
    ],
)
def test_required_qty(line_qty, out_qty, wo_qty, scrap, factor, yld, expected):
    got = required_qty(line_qty, out_qty, wo_qty, scrap_pct=scrap, factor=factor, yield_pct=yld)
    assert got == Decimal(expected)


def test_required_qty_refuses_zero_batch_size():
    with pytest.raises(BusinessRuleError):
        required_qty(1, 0, 5)


def test_cost_receipt_partial_uses_estimate_and_final_takes_residual():
    # The review's failure case: 100 units, ₹1,000 issued, estimate ₹10, receipts of 40 then 60.
    lines = [{"kind": "MAIN", "qty": Decimal("40"), "est_unit": Decimal("10"), "share": Decimal("100")}]
    amounts, residual, exceeds = cost_receipt(pool=Decimal("1000"), lines=lines, is_final=False)
    assert amounts == [Decimal("400.00")] and not exceeds
    lines = [{"kind": "MAIN", "qty": Decimal("60"), "est_unit": Decimal("10"), "share": Decimal("100")}]
    amounts, _r, _e = cost_receipt(pool=Decimal("600"), lines=lines, is_final=True)
    assert amounts == [Decimal("600.00")]


def test_cost_receipt_partial_issue_does_not_underprice():
    # Only ₹400 issued so far; 40 units at ₹10 = ₹400 (not 40% of the pool = ₹160).
    lines = [{"kind": "MAIN", "qty": Decimal("40"), "est_unit": Decimal("10"), "share": Decimal("100")}]
    amounts, _r, exceeds = cost_receipt(pool=Decimal("400"), lines=lines, is_final=False)
    assert amounts == [Decimal("400.00")] and not exceeds


def test_cost_receipt_flags_receipt_beyond_the_pool():
    lines = [{"kind": "MAIN", "qty": Decimal("60"), "est_unit": Decimal("10"), "share": Decimal("100")}]
    _a, _r, exceeds = cost_receipt(pool=Decimal("400"), lines=lines, is_final=False)
    assert exceeds


def test_cost_receipt_final_with_by_product_and_co_product_shares():
    lines = [
        {"kind": "MAIN", "qty": Decimal("80"), "est_unit": Decimal("5"), "share": Decimal("70")},
        {"kind": "CO_PRODUCT", "qty": Decimal("20"), "est_unit": Decimal("5"), "share": Decimal("30")},
        {"kind": "BY_PRODUCT", "qty": Decimal("10"), "recovery": Decimal("2")},
    ]
    amounts, _r, _e = cost_receipt(pool=Decimal("1000"), lines=lines, is_final=True)
    assert amounts[2] == Decimal("20.00")                       # recovery comes off the pool first
    assert amounts[0] == Decimal("686.00")                      # 70 % of the 980 that is left
    assert amounts[1] == Decimal("294.00")                      # the last costed line takes the remainder
    assert sum(amounts) == Decimal("1000.00")                   # nothing is lost


def test_cost_receipt_tolerance_pushes_overflow_to_variance():
    lines = [{"kind": "MAIN", "qty": Decimal("100"), "est_unit": Decimal("10"), "share": Decimal("100")}]
    amounts, residual, _e = cost_receipt(pool=Decimal("1200"), lines=lines, is_final=True, tolerance_pct=Decimal("5"))
    assert amounts == [Decimal("1050.00")] and residual == Decimal("150.00")


# --- roles ------------------------------------------------------------------------------------

def _bom_payload(fg, comp, **kw):
    return {"product": fg.id, "name": "B", "status": "ACTIVE", "lines": [{"component": comp.id, "qty": "2"}], **kw}


def test_role_matrix(tenant_a):
    prepare(tenant_a, separate=False)
    fg = make_product(tenant_a.company, sku="R-FG")
    comp = stocked(tenant_a, "R-COMP", 50, 10)
    bom_resp = tenant_a.client.post("/api/v1/manufacturing/boms/", _bom_payload(fg, comp), format="json")
    assert bom_resp.status_code == 201, bom_resp.data
    bom_id = body(bom_resp)["id"]

    _inv_user, inv = member(tenant_a, "INVENTORY_STAFF", can_manage_inventory=True)
    _acc_user, acc = member(tenant_a, "ACCOUNTANT")
    _aud_user, aud = member(tenant_a, "AUDITOR")
    _view_user, view = member(tenant_a, "VIEWER")
    mgr_user, mgr = member(tenant_a, "MANAGER")

    # Reading: everyone but the sales counter.
    for client in (inv, acc, aud, view, mgr):
        assert client.get("/api/v1/manufacturing/boms/").status_code == 200
    assert tenant_a.staff_client.get("/api/v1/manufacturing/boms/").status_code == 403

    # BOMs: owner and manager write; inventory staff do not.
    assert inv.post("/api/v1/manufacturing/boms/", _bom_payload(fg, comp), format="json").status_code == 403
    assert mgr.post("/api/v1/manufacturing/boms/", _bom_payload(fg, comp, name="M"), format="json").status_code == 201

    # Work orders: inventory staff create and release; viewer and accountant do not.
    wo_body = {"bom": bom_id, "qty": "5"}
    assert view.post("/api/v1/manufacturing/work-orders/", wo_body, format="json").status_code == 403
    assert acc.post("/api/v1/manufacturing/work-orders/", wo_body, format="json").status_code == 403
    created = inv.post("/api/v1/manufacturing/work-orders/", wo_body, format="json")
    assert created.status_code == 201, created.data
    wo_id = body(created)["id"]
    assert inv.post(f"/api/v1/manufacturing/work-orders/{wo_id}/release/").status_code == 200
    # Cancelling is for owner and manager.
    assert inv.post(f"/api/v1/manufacturing/work-orders/{wo_id}/cancel/").status_code == 403
    assert mgr.post(f"/api/v1/manufacturing/work-orders/{wo_id}/cancel/").status_code == 200


def test_costs_are_left_out_for_roles_without_cost_access(tenant_a):
    prepare(tenant_a, separate=False)
    fg = make_product(tenant_a.company, sku="C-FG")
    comp = stocked(tenant_a, "C-COMP", 50, 10)
    bom = make_bom(tenant_a.company, fg, [(comp, 1)], user=tenant_a.owner)
    wo = make_wo(tenant_a.company, bom, 5, user=tenant_a.owner)
    release_work_order(wo, tenant_a.owner)
    _u, inv = member(tenant_a, "INVENTORY_STAFF", can_manage_inventory=True)
    _u2, acc = member(tenant_a, "ACCOUNTANT")
    seen_by_inv = body(inv.get(f"/api/v1/manufacturing/work-orders/{wo.id}/"))
    seen_by_acc = body(acc.get(f"/api/v1/manufacturing/work-orders/{wo.id}/"))
    assert "cost_issued" not in seen_by_inv and "wip_value" not in seen_by_inv   # omitted, not zero
    assert Decimal(seen_by_acc["cost_issued"]) == Decimal("50.00")


# --- BOM revisions ----------------------------------------------------------------------------

def test_activating_a_new_revision_closes_the_old_window_and_moves_the_default(tenant_a):
    company = tenant_a.company
    fg = make_product(company, sku="V-FG")
    comp = stocked(tenant_a, "V-COMP", 10, 5)
    one = make_bom(company, fg, [(comp, 1)], user=tenant_a.owner)
    assert one.revision_no == 1 and one.is_default
    two = bom_svc.create_revision(one, tenant_a.owner, "Switch to a better recipe")
    assert two.status == "DRAFT" and two.revision_no == 2 and two.parent_revision_id == one.id
    assert two.lines.count() == one.lines.count()
    two = bom_svc.activate_revision(two, tenant_a.owner, effective_from=date.today() + timedelta(days=10))
    one.refresh_from_db()
    assert two.is_default and not one.is_default
    assert one.effective_to == date.today() + timedelta(days=9)
    # Until the new one starts, the old recipe is the one in force.
    assert bom_svc.resolve_bom(company, fg, date.today()).pk == one.pk
    assert bom_svc.resolve_bom(company, fg, date.today() + timedelta(days=10)).pk == two.pk


def test_a_revision_cannot_start_before_one_that_already_started(tenant_a):
    company = tenant_a.company
    fg = make_product(company, sku="O-FG")
    comp = stocked(tenant_a, "O-COMP", 10, 5)
    one = make_bom(company, fg, [(comp, 1)], user=tenant_a.owner)
    two = bom_svc.create_revision(one, tenant_a.owner)
    bom_svc.activate_revision(two, tenant_a.owner, effective_from=date.today() + timedelta(days=5))
    three = bom_svc.create_revision(two, tenant_a.owner)
    with pytest.raises(BusinessRuleError) as exc:
        bom_svc.activate_revision(three, tenant_a.owner, effective_from=date.today())
    assert exc.value.get_codes() == "MFG_REVISION_OVERLAP"


def test_customer_revision_wins_over_generic(tenant_a):
    from tests.conftest import make_customer

    company = tenant_a.company
    fg = make_product(company, sku="CU-FG")
    comp = stocked(tenant_a, "CU-COMP", 10, 5)
    generic = make_bom(company, fg, [(comp, 1)], user=tenant_a.owner, name="generic")
    cust = make_customer(company)
    special = make_bom(company, fg, [(comp, 3)], user=tenant_a.owner, name="special", status="DRAFT")
    special.customer = cust
    special.save()
    special = bom_svc.activate_revision(special, tenant_a.owner)
    assert bom_svc.resolve_bom(company, fg, customer=cust).pk == special.pk
    assert bom_svc.resolve_bom(company, fg).pk == generic.pk


def test_no_active_bom_is_a_clear_error(tenant_a):
    fg = make_product(tenant_a.company, sku="N-FG")
    with pytest.raises(BusinessRuleError) as exc:
        bom_svc.resolve_bom(tenant_a.company, fg)
    assert exc.value.get_codes() == "MFG_NO_ACTIVE_BOM"


def test_bom_is_locked_once_a_work_order_uses_it(tenant_a):
    prepare(tenant_a, separate=False)
    fg = make_product(tenant_a.company, sku="L-FG")
    comp = stocked(tenant_a, "L-COMP", 10, 5)
    resp = tenant_a.client.post("/api/v1/manufacturing/boms/", _bom_payload(fg, comp), format="json")
    bom_id = body(resp)["id"]
    assert tenant_a.client.patch(
        f"/api/v1/manufacturing/boms/{bom_id}/", {"lines": [{"component": comp.id, "qty": "3"}]}, format="json",
    ).status_code == 200
    assert tenant_a.client.post("/api/v1/manufacturing/work-orders/", {"bom": bom_id, "qty": "1"}, format="json").status_code == 201
    locked = tenant_a.client.patch(
        f"/api/v1/manufacturing/boms/{bom_id}/", {"lines": [{"component": comp.id, "qty": "9"}]}, format="json",
    )
    assert locked.status_code == 400
    assert "MFG_BOM_LOCKED" in str(locked.data)
    assert tenant_a.client.delete(f"/api/v1/manufacturing/boms/{bom_id}/").status_code == 400
    # A new revision is the way to change it.
    rev = tenant_a.client.post(f"/api/v1/manufacturing/boms/{bom_id}/revise/", {"reason": "More per unit"}, format="json")
    assert rev.status_code == 201 and body(rev)["revision_no"] == 2


def test_bom_validation_rules(tenant_a):
    company = tenant_a.company
    fg = make_product(company, sku="BV-FG")
    comp = stocked(tenant_a, "BV-COMP", 10, 5)
    other = stocked(tenant_a, "BV-OTHER", 10, 5)
    bp = make_product(company, sku="BV-BP", name="By")
    kg = bom_unit = None
    from masters.models import Unit

    kg = Unit.objects.create(company=company, name="Kilogram", short_name="kg")
    gm = Unit.objects.create(company=company, name="Gram", short_name="g")
    comp.unit = kg
    comp.save()
    base = {"product": fg.id, "name": "X", "status": "DRAFT"}

    def post(payload):
        return tenant_a.client.post("/api/v1/manufacturing/boms/", {**base, **payload}, format="json")

    # A unit that is not the component's own or alternate unit.
    bad_unit = post({"lines": [{"component": comp.id, "qty": "1", "unit": gm.id}]})
    assert bad_unit.status_code == 400 and "MFG_BAD_LINE_UNIT" in str(bad_unit.data)
    # Co-product shares above 100.
    shares = post({
        "lines": [{"component": comp.id, "qty": "1"}],
        "outputs": [
            {"product": bp.id, "kind": "CO_PRODUCT", "qty": "1", "cost_share_pct": "60"},
            {"product": other.id, "kind": "CO_PRODUCT", "qty": "1", "cost_share_pct": "60"},
        ],
    })
    assert shares.status_code == 400 and "MFG_BAD_COST_SHARE" in str(shares.data)
    # An output that is also a component.
    clash = post({
        "lines": [{"component": comp.id, "qty": "1"}],
        "outputs": [{"product": comp.id, "kind": "BY_PRODUCT", "qty": "1"}],
    })
    assert clash.status_code == 400 and "MFG_OUTPUT_IS_COMPONENT" in str(clash.data)
    # By-products carry no cost share.
    share_on_byproduct = post({
        "lines": [{"component": comp.id, "qty": "1"}],
        "outputs": [{"product": bp.id, "kind": "BY_PRODUCT", "qty": "1", "cost_share_pct": "10"}],
    })
    assert share_on_byproduct.status_code == 400
    ok = post({
        "lines": [{"component": comp.id, "qty": "1"}],
        "outputs": [{"product": bp.id, "kind": "BY_PRODUCT", "qty": "2", "recovery_rate": "1.5"}],
        "additional_costs": [{"label": "Packing", "basis": "PER_BATCH", "amount": "50"}],
        "output_qty": "100", "yield_pct": "98",
    })
    assert ok.status_code == 201, ok.data
    assert body(ok)["outputs"][0]["kind"] == "BY_PRODUCT"


def test_batch_recipe_snapshot_uses_batch_size_scrap_and_yield(tenant_a):
    prepare(tenant_a, separate=False)
    company = tenant_a.company
    fg = make_product(company, sku="S-FG")
    comp = stocked(tenant_a, "S-COMP", 1000, 2)
    bom = make_bom(
        company, fg,
        [{"component": comp, "qty": Decimal("62"), "scrap_pct": Decimal("2")}],
        user=tenant_a.owner, output_qty="100", yield_pct="98",
    )
    wo = make_wo(company, bom, 250, user=tenant_a.owner)
    line = wo.component_lines.get()
    assert line.qty == required_qty(62, 100, 250, scrap_pct=2, yield_pct=98)
    assert line.qty_per_unit == Decimal("0.620")


# --- DEF fixes --------------------------------------------------------------------------------

@pytest.fixture(params=["WAVG", "FIFO"])
def method(request):
    return request.param


def test_wavg_outbound_movement_records_the_cost_the_pool_actually_consumed(tenant_a):
    prepare(tenant_a, method="WAVG", separate=False)
    comp = make_product(tenant_a.company, sku="W-COMP", purchase_price="10")
    add_stock(tenant_a, comp, "10", unit_cost="10")
    InventoryService.post_movement(
        company=tenant_a.company, product=comp, movement_type=MovementType.PURCHASE, quantity=Decimal("10"),
        unit_cost=Decimal("20"), user=tenant_a.owner,
    )
    # The caller hands in a stale ₹99; the pool's average is ₹15.
    move = InventoryService.post_movement(
        company=tenant_a.company, product=comp, movement_type=MovementType.MANUFACTURE_ISSUE,
        quantity=Decimal("4"), unit_cost=Decimal("99"), user=tenant_a.owner,
    )
    move.refresh_from_db()
    assert move.unit_cost == Decimal("15.0000")


def test_def1_completion_without_material_cost_is_refused(tenant_a, method):
    prepare(tenant_a, method=method, separate=False)
    company = tenant_a.company
    fg = make_product(company, sku="D1-FG")
    comp = stocked(tenant_a, "D1-COMP", 10, 0)       # stock on hand, but with no cost on record
    bom = make_bom(company, fg, [(comp, 1)], user=tenant_a.owner)
    wo = make_wo(company, bom, 2, user=tenant_a.owner)
    release_work_order(wo, tenant_a.owner)
    wo.refresh_from_db()
    with pytest.raises(BusinessRuleError) as exc:
        complete_work_order(wo, tenant_a.owner)
    assert exc.value.get_codes() == "MFG_ZERO_COST_COMPLETE"
    assert not StockMovement.objects.filter(movement_type=MovementType.MANUFACTURE_RECEIPT).exists()


def test_def1_books_equal_what_went_into_stock_and_rounding_goes_to_variance(tenant_a, method):
    prepare(tenant_a, method=method, separate=False)
    company = tenant_a.company
    fg = make_product(company, sku="D1R-FG")
    comp = stocked(tenant_a, "D1R-COMP", 100, "3.3333")
    comp2 = stocked(tenant_a, "D1R-COMP2", 100, "0.0077")
    bom = make_bom(company, fg, [(comp, 1), (comp2, 1)], user=tenant_a.owner)
    wo = make_wo(company, bom, 7, user=tenant_a.owner)
    release_work_order(wo, tenant_a.owner)
    wo.refresh_from_db()
    complete_work_order(wo, tenant_a.owner)
    wo.refresh_from_db()
    receipt = StockMovement.objects.get(movement_type=MovementType.MANUFACTURE_RECEIPT)
    stock_value = (receipt.unit_cost * receipt.quantity).quantize(Decimal("0.01"))
    assert wo.cost_received == stock_value
    assert wo.cost_received + wo.cost_variance == wo.cost_issued
    # Work in progress is empty, and whatever the rounding left over sits in variance, not nowhere.
    assert account_net(company, "1450") == Decimal("0.00")
    assert account_net(company, "1400") + account_net(company, "5420") == Decimal("0.00")


def test_def2_components_are_consumed_not_scrapped_and_come_back_on_cancel(tenant_a, method):
    prepare(tenant_a, method=method, separate=False)
    company = tenant_a.company
    fg = make_product(company, sku="D2-FG")
    comp = make_product(company, sku="D2-COMP", purchase_price="10", track_serial=True)
    from inventory.services import SerialNumberService

    wh = InventoryService.default_warehouse(company)
    SerialNumberService.receive(company=company, product=comp, warehouse=wh, numbers=["S1", "S2"], quantity=2)
    add_stock(tenant_a, comp, "2", unit_cost="10")
    bom = make_bom(company, fg, [(comp, 1)], user=tenant_a.owner)
    wo = make_wo(company, bom, 2, user=tenant_a.owner)
    line = wo.component_lines.get()
    line.serial_numbers = ["S1", "S2"]
    line.save()
    release_work_order(wo, tenant_a.owner)
    assert set(SerialNumber.objects.filter(product=comp).values_list("status", flat=True)) == {"CONSUMED"}
    links = TraceLink.objects.filter(work_order_id=wo.id, input_product=comp)
    assert sorted(links.values_list("input_serial", flat=True)) == ["S1", "S2"]
    wo.refresh_from_db()
    cancel_work_order(wo, tenant_a.owner)
    assert set(SerialNumber.objects.filter(product=comp).values_list("status", flat=True)) == {"AVAILABLE"}
    assert not TraceLink.objects.filter(work_order_id=wo.id, reversed_at__isnull=True).exists()


def test_def3_cancel_posts_manufacturing_reversals_not_adjustments(tenant_a, method):
    prepare(tenant_a, method=method, separate=False)
    company = tenant_a.company
    fg = make_product(company, sku="D3-FG")
    comp = stocked(tenant_a, "D3-COMP", 20, 10)
    bom = make_bom(company, fg, [(comp, 2)], user=tenant_a.owner)
    wo = make_wo(company, bom, 3, user=tenant_a.owner)
    release_work_order(wo, tenant_a.owner)
    wo.refresh_from_db()
    complete_work_order(wo, tenant_a.owner)
    wo.refresh_from_db()
    cancel_work_order(wo, tenant_a.owner)
    types = set(
        StockMovement.objects.filter(reference_type="work_order_cancel").values_list("movement_type", flat=True)
    )
    assert types == {MovementType.MANUFACTURE_REVERSAL}
    assert not StockMovement.objects.filter(
        movement_type=MovementType.ADJUSTMENT, reference_type="work_order_cancel",
    ).exists()
    # Stock is back where it started, and nothing is left in work in progress.
    assert StockBalance.objects.get(company=company, product=comp).on_hand == Decimal("20")
    assert StockBalance.objects.get(company=company, product=fg).on_hand == Decimal("0")
    assert account_net(company, "1450") == Decimal("0.00")


# --- godowns, registry, product role ----------------------------------------------------------

def test_selectable_godowns_keep_job_worker_and_quarantine_out_of_sales_and_counts(tenant_a):
    company = tenant_a.company
    normal = InventoryService.default_warehouse(company)
    qrn = Warehouse.objects.create(company=company, name="Q", code="Q1", kind="QUARANTINE")
    jw = Warehouse.objects.create(company=company, name="At Ravi", code="JW1", kind="JOB_WORKER")
    scr = Warehouse.objects.create(company=company, name="S", code="S1", kind="SCRAP")
    sale = set(Warehouse.objects.selectable("SALE", company).values_list("pk", flat=True))
    assert sale == {normal.pk}
    assert set(Warehouse.objects.selectable("COUNT", company).values_list("pk", flat=True)) == {normal.pk, qrn.pk}
    assert jw.pk not in Warehouse.objects.selectable("TRANSFER", company).values_list("pk", flat=True)
    assert scr.pk in Warehouse.objects.selectable("MFG_RECEIPT", company).values_list("pk", flat=True)
    # The list endpoint leaves a job-worker godown out; a purpose narrows it further.
    ids = {w["id"] for w in rows(tenant_a.client.get("/api/v1/inventory/warehouses/"))}
    assert jw.pk not in ids and qrn.pk in ids
    sale_ids = {w["id"] for w in rows(tenant_a.client.get("/api/v1/inventory/warehouses/?purpose=SALE"))}
    assert sale_ids == {normal.pk}
    # Nobody counts stock at a job worker from the count screen.
    resp = tenant_a.client.post("/api/v1/inventory/stock-counts/", {"warehouse": jw.pk, "notes": ""}, format="json")
    assert resp.status_code == 400


def test_every_reference_type_manufacturing_uses_is_registered():
    from inventory.costing_refs import MANUFACTURING_REFS

    root = Path(__file__).resolve().parents[1]
    found = set()
    for app in ("manufacturing", "jobwork"):
        for path in (root / app).rglob("*.py"):
            if "migrations" in path.parts:
                continue
            found |= set(re.findall(r'reference_type\s*=\s*"([a-z_]+)"', path.read_text(encoding="utf-8")))
    # A conditional like `"mfg_backflush" if x else "mfg_issue"` is picked up by the second pattern.
    for path in (root / "manufacturing").rglob("*.py"):
        found |= set(re.findall(r'reference_type=\s*"([a-z_]+)"\s+if', path.read_text(encoding="utf-8")))
    found -= {"sales_invoice"}  # a read filter in the profitability report, never a movement the module writes
    assert found - MANUFACTURING_REFS == set(), f"unregistered reference types: {found - MANUFACTURING_REFS}"


def test_product_manufacturing_role_is_editable(tenant_a):
    p = make_product(tenant_a.company, sku="ROLE-1")
    resp = tenant_a.client.patch(f"/api/v1/products/{p.id}/", {"mfg_role": "RAW"}, format="json")
    assert resp.status_code == 200, resp.data
    p.refresh_from_db()
    assert p.mfg_role == "RAW"


def test_settings_endpoint_and_mode_switch_guard(tenant_a):
    prepare(tenant_a, separate=False)
    got = tenant_a.client.get("/api/v1/manufacturing/settings/")
    assert got.status_code == 200 and body(got)["default_issue_mode"] == "AUTO_AT_RELEASE"
    ok = tenant_a.client.patch("/api/v1/manufacturing/settings/", {"default_issue_mode": "SEPARATE", "backdate_days": 3}, format="json")
    assert ok.status_code == 200 and body(ok)["backdate_days"] == 3
    _u, inv = member(tenant_a, "INVENTORY_STAFF", can_manage_inventory=True)
    assert inv.patch("/api/v1/manufacturing/settings/", {"backdate_days": 1}, format="json").status_code == 403
    # With a released order, the mode cannot be switched.
    prepare(tenant_a, separate=False)
    fg = make_product(tenant_a.company, sku="SW-FG")
    comp = stocked(tenant_a, "SW-COMP", 10, 5)
    wo = make_wo(tenant_a.company, make_bom(tenant_a.company, fg, [(comp, 1)], user=tenant_a.owner), 1, user=tenant_a.owner)
    release_work_order(wo, tenant_a.owner)
    blocked = tenant_a.client.patch("/api/v1/manufacturing/settings/", {"default_issue_mode": "SEPARATE"}, format="json")
    assert blocked.status_code == 400 and "MFG_MODE_SWITCH_BLOCKED" in str(blocked.data)


def test_data_migration_numbers_existing_duplicate_active_boms(tenant_a):
    """B8-018: two ACTIVE BOMs for one product become revisions 1 and 2, newest default."""
    import importlib

    from django.apps import apps

    company = tenant_a.company
    fg = make_product(company, sku="MIG-FG")
    comp = stocked(tenant_a, "MIG-COMP", 10, 5)
    old = Bom.objects.create(company=company, product=fg, name="old", status="ACTIVE", revision_no=7)
    new = Bom.objects.create(company=company, product=fg, name="new", status="ACTIVE", revision_no=9)
    mod = importlib.import_module("manufacturing.migrations.0012_mfg_phase0_data")
    mod.number_bom_revisions(apps, None)
    old.refresh_from_db()
    new.refresh_from_db()
    assert (old.revision_no, new.revision_no) == (1, 2)
    assert new.is_default and not old.is_default
    mod.number_bom_revisions(apps, None)   # running it twice changes nothing
    new.refresh_from_db()
    assert new.revision_no == 2 and new.is_default


def test_every_error_code_in_manufacturing_is_documented():
    from manufacturing.error_codes import ERROR_CODES, NOT_ERROR_CODES

    root = Path(__file__).resolve().parents[1] / "manufacturing"
    used = set()
    for path in root.rglob("*.py"):
        if "migrations" in path.parts or path.name == "error_codes.py":
            continue
        used |= set(re.findall(r'"((?:MFG|JW)_[A-Z_]+)"', path.read_text(encoding="utf-8")))
    undocumented = used - set(ERROR_CODES) - NOT_ERROR_CODES
    assert undocumented == set(), f"error codes without a description: {sorted(undocumented)}"
