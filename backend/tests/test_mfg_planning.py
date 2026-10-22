"""Manufacturing phase 2: explosion, availability, alternates, MRP, make-to-order, the board."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.invariants import assert_all_invariants
from inventory.models import StockBalance, StockReservation, WarehouseReorderLevel
from inventory.services import InventoryService
from manufacturing.models import Bom, BomLine, MrpLine, MrpRun
from manufacturing.services import flow, issue as issue_svc, planning, receipt as receipt_svc, release_work_order
from tests.conftest import add_stock, make_customer, make_product, make_supplier
from tests.mfg_helpers import body, make_bom, make_wo, member, prepare, stocked

pytestmark = pytest.mark.django_db


def D(v):
    return Decimal(str(v))


@pytest.fixture(params=["WAVG", "FIFO"])
def method(request):
    return request.param


def planning_on(tenant):
    flags = dict(tenant.company.feature_flags or {})
    flags["MFG_PLANNING"] = True
    tenant.company.feature_flags = flags
    tenant.company.save(update_fields=["feature_flags"])


# --- multi-level recipes -------------------------------------------------------------------------

def tree(tenant):
    """A needs 2 B and 1 C. B needs 3 D. D costs 5, C costs 7."""
    c = tenant.company
    a = make_product(c, sku="A", name="A")
    b = make_product(c, sku="B", name="B")
    cc = stocked(tenant, "C", 100, 7)
    dd = stocked(tenant, "D", 1000, 5)
    make_bom(c, b, [(dd, 3)], user=tenant.owner, name="B")
    make_bom(c, a, [(b, 2), (cc, 1)], user=tenant.owner, name="A")
    return a, b, cc, dd


def test_explode_opens_every_level(tenant_a, method):
    prepare(tenant_a, method=method)
    a, b, cc, dd = tree(tenant_a)
    rows = planning.explode(tenant_a.company, a, 10)
    flat = [(r["level"], r["product"].sku, r["qty"]) for r in rows]
    assert (1, "B", D(20)) in flat and (1, "C", D(10)) in flat
    assert (2, "D", D(60)) in flat                         # 10 A -> 20 B -> 60 D
    one_level = planning.explode(tenant_a.company, a, 10, expand="none")
    assert len(one_level) == 2 and all(r["level"] == 1 for r in one_level)


def test_where_used_walks_up_to_the_top(tenant_a, method):
    prepare(tenant_a, method=method)
    a, b, cc, dd = tree(tenant_a)
    used = planning.where_used(tenant_a.company, dd)
    assert [(u["level"], u["product"]) for u in used] == [(1, "B"), (2, "A")]


def test_cost_rollup_goes_down_through_sub_assemblies(tenant_a, method):
    prepare(tenant_a, method=method)
    a, b, cc, dd = tree(tenant_a)
    assert planning.rollup_cost(tenant_a.company, b)["unit_cost"] == D("15.0000")        # 3 x 5
    got = planning.rollup_cost(tenant_a.company, a, qty=4)
    assert got["unit_cost"] == D("37.0000") and got["total"] == D("148.00")              # 2 x 15 + 7


def test_a_loop_found_while_exploding_is_refused_not_followed(tenant_a):
    prepare(tenant_a)
    c = tenant_a.company
    x, y = make_product(c, sku="X"), make_product(c, sku="Y")
    make_bom(c, x, [(y, 1)], user=tenant_a.owner)
    # Bypass the save-time check the way an import or a data fix could.
    bom_y = Bom.objects.create(company=c, product=y, name="Y", status="ACTIVE", revision_no=1, is_default=True)
    BomLine.objects.create(bom=bom_y, company=c, component=x, qty=D(1))
    with pytest.raises(BusinessRuleError) as exc:
        planning.explode(c, x, 1)
    assert exc.value.get_codes() == "MFG_BOM_CYCLE"


def test_a_kit_is_looked_through_when_the_order_is_made(tenant_a, method):
    prepare(tenant_a, method=method)
    c = tenant_a.company
    fg, kit = make_product(c, sku="KFG"), make_product(c, sku="KIT")
    screw = stocked(tenant_a, "SCREW", 500, 1)
    make_bom(c, kit, [(screw, 4)], user=tenant_a.owner)
    bom = make_bom(c, fg, [{"component": kit, "qty": D(2), "is_phantom": True}], user=tenant_a.owner)
    wo = make_wo(c, bom, 10, user=tenant_a.owner)
    lines = list(wo.component_lines.values_list("component__sku", "qty"))
    assert lines == [("SCREW", D("80.000"))]                 # 10 x 2 kits x 4 screws; the kit itself is not a line


def test_how_many_can_i_make_names_the_limit(tenant_a, method):
    prepare(tenant_a, method=method)
    c = tenant_a.company
    fg = make_product(c, sku="CM-FG")
    b, cc = stocked(tenant_a, "CM-B", 10, 1), stocked(tenant_a, "CM-C", 3, 1)
    make_bom(c, fg, [(b, 2), (cc, 1)], user=tenant_a.owner)
    got = planning.max_producible(c, fg)
    assert got["qty"] == D("3.000") and got["limited_by"] == cc.pk


def test_how_many_can_i_make_looks_through_a_kit_to_the_real_material(tenant_a, method):
    prepare(tenant_a, method=method)
    c = tenant_a.company
    fg, kit = make_product(c, sku="CK-FG"), make_product(c, sku="CK-KIT")
    screw = stocked(tenant_a, "CK-SCREW", 80, 1)
    make_bom(c, kit, [(screw, 4)], user=tenant_a.owner)
    make_bom(c, fg, [{"component": kit, "qty": D(2), "is_phantom": True}], user=tenant_a.owner)
    # Each FG takes 2 kits of 4 screws: 8 screws. 80 screws make 10, and the kit (never in stock) is not the limit.
    got = planning.max_producible(c, fg)
    assert got["qty"] == D("10.000") and got["limited_by"] == screw.pk


# --- availability and alternates ----------------------------------------------------------------

def test_a_released_order_sees_its_own_hold_as_available(tenant_a, method):
    prepare(tenant_a, method=method)
    c = tenant_a.company
    fg, comp = make_product(c, sku="AV-FG"), stocked(tenant_a, "AV-C", 60, 10)
    bom = make_bom(c, fg, [(comp, 1)], user=tenant_a.owner)
    wo = release_work_order(make_wo(c, bom, 100, user=tenant_a.owner), tenant_a.owner)
    row = planning.work_order_availability(wo)[0]
    assert (row["need"], row["held"], row["short"]) == (D(100), D(60), D(40))


def test_open_orders_share_stock_in_due_date_order(tenant_a, method):
    prepare(tenant_a, method=method)
    c = tenant_a.company
    fg, comp = make_product(c, sku="SH-FG"), stocked(tenant_a, "SH-C", 100, 10)
    bom = make_bom(c, fg, [(comp, 1)], user=tenant_a.owner)
    today = timezone.localdate()
    late = make_wo(c, bom, 50, user=tenant_a.owner, due_date=today + timedelta(days=20))
    early = make_wo(c, bom, 80, user=tenant_a.owner, due_date=today + timedelta(days=3))
    for wo in (late, early):
        release_work_order(wo, tenant_a.owner)
    out = planning.open_order_shortages(c)
    assert len(out) == 1 and out[0]["work_order"].pk == late.pk        # the early order gets its 80; the late one is 30 short
    assert out[0]["lines"][0]["short"] == D(30)


def alt_setup(tenant, method):
    prepare(tenant, method=method)
    c = tenant.company
    fg = make_product(c, sku="ALT-FG")
    primary, alt = stocked(tenant, "ALT-P", 5, 10), stocked(tenant, "ALT-S", 100, 12)
    bom = make_bom(c, fg, [
        {"component": primary, "qty": D(1), "alternate_group": 1, "alternate_priority": 1},
        {"component": alt, "qty": D(1), "alternate_group": 1, "alternate_priority": 2},
    ], user=tenant.owner)
    wo = release_work_order(make_wo(c, bom, 20, user=tenant.owner), tenant.owner)
    return c, fg, primary, alt, wo


def test_an_alternate_is_not_a_second_requirement(tenant_a, method):
    c, fg, primary, alt, wo = alt_setup(tenant_a, method)
    lines = {ln.component.sku: ln for ln in wo.component_lines.select_related("component")}
    assert lines["ALT-S"].alternate_of_id == lines["ALT-P"].pk and lines["ALT-P"].alternate_of_id is None
    # Only the primary is held and only the primary is asked for by default.
    assert not StockReservation.objects.filter(product=alt, reference_type="work_order").exists()
    draft = issue_svc.create_issue(wo, tenant_a.owner)
    assert [ln.component.sku for ln in draft.lines.all()] == ["ALT-P"]


def test_shortage_points_at_the_alternate_in_stock(tenant_a, method):
    c, fg, primary, alt, wo = alt_setup(tenant_a, method)
    row = planning.work_order_availability(wo)[0]
    assert row["short"] == D(15) and [a["product"].sku for a in row["alternates"]] == ["ALT-S"]


def test_issuing_the_alternate_in_place_of_the_primary(tenant_a, method):
    c, fg, primary, alt, wo = alt_setup(tenant_a, method)
    primary_line = wo.component_lines.get(component=primary)
    doc = issue_svc.create_issue(wo, tenant_a.owner, [
        {"wo_line": primary_line, "qty": 5},
        {"wo_line": primary_line, "component": alt, "qty": 15},
    ])
    issue_svc.post_issue(doc, tenant_a.owner)
    wo.refresh_from_db()
    primary_line.refresh_from_db()
    assert primary_line.qty_issued == D(20) and primary_line.qty_remaining == 0
    assert StockBalance.objects.get(company=c, product=alt).on_hand == D(85)
    receipt_svc.post_receipt(receipt_svc.create_receipt(wo, tenant_a.owner, {"is_final": True}), tenant_a.owner)
    wo.refresh_from_db()
    closed = flow.close_work_order(wo, tenant_a.owner)
    sub = closed.variances.get(kind="SUBSTITUTION")
    assert sub.component_id == alt.pk and sub.actual_qty == D(15) and sub.actual_cost == D("180.00")
    usage = closed.variances.get(kind="USAGE")
    assert usage.actual_qty == D(20)                       # the swap is counted against the line it stood in for
    assert_all_invariants(c)


def test_only_a_listed_alternate_may_stand_in(tenant_a, method):
    c, fg, primary, alt, wo = alt_setup(tenant_a, method)
    stranger = stocked(tenant_a, "ALT-X", 50, 1)
    primary_line = wo.component_lines.get(component=primary)
    with pytest.raises(BusinessRuleError) as exc:
        issue_svc.create_issue(wo, tenant_a.owner, [{"wo_line": primary_line, "component": stranger, "qty": 1}])
    assert exc.value.get_codes() == "MFG_NOT_AN_ALTERNATE"


# --- material requirements planning --------------------------------------------------------------

def confirmed_order(tenant, customer, product, qty, due):
    from sales.models import SalesInvoice, SalesOrder
    from sales.notes_services import SalesNotesService

    order = SalesOrder.objects.create(
        company=tenant.company, customer=customer, invoice_type=SalesInvoice.InvoiceType.NON_GST,
        expected_delivery=due, created_by=tenant.owner, updated_by=tenant.owner,
    )
    SalesNotesService.set_order_items(
        order, [{"product": product, "quantity": D(qty), "unit_price": D(100), "gst_rate": 0}], tenant.owner,
    )
    SalesNotesService.confirm_sales_order(order, tenant.owner)
    order.refresh_from_db()
    return order


def purchase_order_draft(tenant, supplier, product, qty):
    from purchases.models import PurchaseOrder
    from purchases.notes_services import PurchaseNotesService

    po = PurchaseOrder.objects.create(company=tenant.company, supplier=supplier, created_by=tenant.owner, updated_by=tenant.owner)
    PurchaseNotesService.set_order_items(po, [{"product": product, "quantity": D(qty)}], tenant.owner)
    return po


def mrp_world(tenant, method):
    prepare(tenant, method=method)
    c = tenant.company
    c.negative_stock_policy = "WARN"        # a confirmed sales order may hold more than is on hand
    c.save(update_fields=["negative_stock_policy"])
    fg = make_product(c, sku="MRP-FG", name="Finished")
    raw = make_product(c, sku="MRP-RAW", name="Raw", purchase_price="10")
    add_stock(tenant, fg, "20", unit_cost="30")
    add_stock(tenant, raw, "30", unit_cost="10")
    make_bom(c, fg, [(raw, 1)], user=tenant.owner)
    wh = InventoryService.default_warehouse(c)
    WarehouseReorderLevel.objects.create(company=c, warehouse=wh, product=raw, lead_time_days=5)
    customer = make_customer(c)
    due = timezone.localdate() + timedelta(days=10)
    order = confirmed_order(tenant, customer, fg, 100, due)
    return c, fg, raw, order, due


def test_mrp_nets_demand_against_stock_and_incoming_and_explodes_what_it_makes(tenant_a, method):
    c, fg, raw, order, due = mrp_world(tenant_a, method)
    supplier = make_supplier(c)
    purchase_order_draft(tenant_a, supplier, raw, 20)
    run = planning.run_mrp(c, tenant_a.owner, horizon_days=30)
    by_sku = {ln.product.sku: ln for ln in run.lines.select_related("product")}
    make_line, buy_line = by_sku["MRP-FG"], by_sku["MRP-RAW"]
    assert make_line.kind == "MAKE" and make_line.net_qty == D(80)          # 100 wanted - 20 on hand
    assert make_line.need_date == due and make_line.level == 0
    # Making 80 needs 80 raw: 30 on hand and 20 on order leave 30 to buy, to be ordered 5 days ahead.
    assert buy_line.kind == "PURCHASE" and buy_line.gross_qty == D(80)
    assert (buy_line.on_hand_qty, buy_line.incoming_qty, buy_line.net_qty) == (D(30), D(20), D(30))
    assert buy_line.order_by == due - timedelta(days=5) and buy_line.level == 1
    assert run.summary == {"lines": 2, "purchase": 1, "make": 1}


def test_safety_stock_is_wanted_on_top_of_demand(tenant_a, method):
    c, fg, raw, order, due = mrp_world(tenant_a, method)
    WarehouseReorderLevel.objects.filter(product=raw).update(safety_stock_qty=D(10))
    run = planning.run_mrp(c, tenant_a.owner)
    buy = run.lines.get(product=raw)
    assert buy.safety_qty == D(10) and buy.net_qty == D(60)        # 80 + 10 - 30


def test_nothing_is_suggested_when_stock_covers_demand(tenant_a, method):
    c, fg, raw, order, due = mrp_world(tenant_a, method)
    InventoryService.post_movement(
        company=c, product=fg, movement_type="PURCHASE", quantity=D(500), unit_cost=D(30), user=tenant_a.owner,
    )
    run = planning.run_mrp(c, tenant_a.owner)
    assert run.lines.count() == 0


def test_horizon_leaves_out_demand_that_is_further_away(tenant_a, method):
    c, fg, raw, order, due = mrp_world(tenant_a, method)
    assert planning.run_mrp(c, tenant_a.owner, horizon_days=5).lines.count() == 0
    assert planning.run_mrp(c, tenant_a.owner, horizon_days=15).lines.count() == 2


def test_a_new_run_supersedes_the_last(tenant_a, method):
    c, fg, raw, order, due = mrp_world(tenant_a, method)
    first = planning.run_mrp(c, tenant_a.owner)
    second = planning.run_mrp(c, tenant_a.owner)
    first.refresh_from_db()
    assert first.status == MrpRun.Status.SUPERSEDED and second.status == MrpRun.Status.DONE


def test_converting_suggestions_makes_draft_orders_and_is_not_repeatable(tenant_a, method):
    from purchases.models import PurchaseOrder

    c, fg, raw, order, due = mrp_world(tenant_a, method)
    supplier = make_supplier(c, name="Dry goods Co")
    run = planning.run_mrp(c, tenant_a.owner)
    buy = run.lines.get(product=raw)
    result = planning.convert_mrp_lines(run, tenant_a.owner, supplier_overrides={buy.pk: supplier.pk})
    assert len(result["work_orders"]) == 1 and len(result["purchase_orders"]) == 1
    wo = result["work_orders"][0]
    assert wo.qty == D(80) and wo.due_date == due and wo.status == "DRAFT"
    po = PurchaseOrder.objects.get(company=c, supplier=supplier)
    assert po.items.get().quantity == D(50) and po.status == "DRAFT"
    run.lines.get(product=fg).refresh_from_db()
    assert not MrpLine.objects.filter(run=run, status="OPEN").exists()
    again = planning.convert_mrp_lines(run, tenant_a.owner)
    assert again["work_orders"] == [] and again["purchase_orders"] == []


def test_a_purchase_line_without_a_supplier_is_skipped_with_a_reason(tenant_a, method):
    c, fg, raw, order, due = mrp_world(tenant_a, method)
    run = planning.run_mrp(c, tenant_a.owner)
    result = planning.convert_mrp_lines(run, tenant_a.owner)
    line = run.lines.get(product=raw)
    line.refresh_from_db()
    assert line.status == "SKIPPED" and "supplier" in line.note.lower() and len(result["skipped"]) == 1


def test_the_supplier_comes_from_the_last_purchase_of_the_item(tenant_a, method):
    from tests.conftest import create_draft_purchase

    c, fg, raw, order, due = mrp_world(tenant_a, method)
    supplier = make_supplier(c, name="Usual Supplier", gstin="29AAAAA0000A1ZY")
    bill = create_draft_purchase(
        tenant_a, supplier, [{"product": raw.id, "quantity": "5", "unit_price": "10", "gst_rate": "0"}], purchase_type="NON_GST",
    )
    assert bill["id"]
    run = planning.run_mrp(c, tenant_a.owner)
    assert run.lines.get(product=raw).supplier_id == supplier.pk


# --- make to order ------------------------------------------------------------------------------

def test_work_orders_are_made_from_a_sales_order_and_pegged_to_its_lines(tenant_a, method):
    c, fg, raw, order, due = mrp_world(tenant_a, method)
    created, skipped = planning.create_orders_from_sales_order(order, tenant_a.owner)
    assert len(created) == 1 and created[0].qty == D(100) and created[0].sales_order_id == order.pk
    assert created[0].due_date == due and created[0].sales_order_item_id
    again, skipped2 = planning.create_orders_from_sales_order(order, tenant_a.owner)
    assert again == [] and skipped2[0]["reason"] == "Already planned"       # asking twice does not double the plan
    status = planning.production_status_for_order(order)[0]
    assert status["ordered"] == D(100) and status["planned"] == D(100) and status["made"] == 0
    assert status["work_orders"][0]["number"].startswith("WO-")


def test_a_line_without_a_recipe_is_reported_not_guessed(tenant_a):
    prepare(tenant_a)
    c = tenant_a.company
    plain = stocked(tenant_a, "NOREC", 50, 1)
    order = confirmed_order(tenant_a, make_customer(c), plain, 5, timezone.localdate() + timedelta(days=3))
    created, skipped = planning.create_orders_from_sales_order(order, tenant_a.owner)
    assert created == [] and skipped[0]["reason"] == "No recipe"


def test_available_to_promise_counts_stock_coming_by_the_date(tenant_a, method):
    c, fg, raw, order, due = mrp_world(tenant_a, method)
    today = timezone.localdate()
    wo = make_wo(c, Bom.objects.get(product=fg), 50, user=tenant_a.owner, due_date=today + timedelta(days=4))
    release_work_order(wo, tenant_a.owner)
    soon = planning.available_to_promise(c, fg, today + timedelta(days=5))
    assert soon["supply"] == D(70) and soon["available"] == D(70)            # 20 on hand + 50 due by then; the order is later
    later = planning.available_to_promise(c, fg, due)
    assert later["committed"] == D(100) and later["available"] == 0


# --- the board ----------------------------------------------------------------------------------

def test_board_flags_late_soon_and_short_orders(tenant_a, method):
    prepare(tenant_a, method=method)
    c = tenant_a.company
    fg, comp = make_product(c, sku="BD-FG"), stocked(tenant_a, "BD-C", 10, 1)
    bom = make_bom(c, fg, [(comp, 1)], user=tenant_a.owner)
    today = timezone.localdate()
    late = release_work_order(make_wo(c, bom, 5, user=tenant_a.owner, due_date=today - timedelta(days=2)), tenant_a.owner)
    soon = release_work_order(make_wo(c, bom, 5, user=tenant_a.owner, due_date=today + timedelta(days=1)), tenant_a.owner)
    short = release_work_order(make_wo(c, bom, 500, user=tenant_a.owner, due_date=today + timedelta(days=30)), tenant_a.owner)
    rows = {r["id"]: r for r in planning.board(c)}
    assert rows[late.pk]["late"] and not rows[late.pk]["due_soon"]
    assert rows[soon.pk]["due_soon"] and not rows[soon.pk]["late"]
    assert rows[short.pk]["short_material"]
    assert not rows[late.pk]["short_material"] and not rows[soon.pk]["short_material"]


# --- API: gating, roles and the endpoints ----------------------------------------------------------

def test_planning_endpoints_are_dark_until_the_flag_is_on(tenant_a):
    prepare(tenant_a)
    assert tenant_a.client.get("/api/v1/manufacturing/mrp-runs/").status_code == 404
    assert tenant_a.client.get("/api/v1/manufacturing/board/").status_code == 404
    planning_on(tenant_a)
    assert tenant_a.client.get("/api/v1/manufacturing/mrp-runs/").status_code == 200


def test_planning_api_end_to_end(tenant_a):
    c, fg, raw, order, due = mrp_world(tenant_a, "WAVG")
    planning_on(tenant_a)
    api = tenant_a.client
    run = api.post("/api/v1/manufacturing/mrp-runs/run/", {"horizon_days": 30}, format="json")
    assert run.status_code == 201 and body(run)["summary"]["make"] == 1
    run_id = body(run)["id"]
    supplier = make_supplier(c, name="API Supplier")
    buy_id = next(ln["id"] for ln in body(run)["lines"] if ln["kind"] == "PURCHASE")
    conv = api.post(
        f"/api/v1/manufacturing/mrp-runs/{run_id}/convert/", {"suppliers": {str(buy_id): supplier.pk}}, format="json",
    )
    assert conv.status_code == 201 and len(body(conv)["work_orders"]) == 1 and len(body(conv)["purchase_orders"]) == 1
    # A superseded run cannot be converted.
    api.post("/api/v1/manufacturing/mrp-runs/run/", {}, format="json")
    assert api.post(f"/api/v1/manufacturing/mrp-runs/{run_id}/convert/", {}, format="json").status_code == 400
    assert api.get(f"/api/v1/manufacturing/can-make/?product={fg.pk}").status_code == 200
    assert api.get(f"/api/v1/manufacturing/explode/?product={fg.pk}&qty=10").status_code == 200
    assert api.get(f"/api/v1/manufacturing/where-used/?product={raw.pk}").status_code == 200
    assert api.get(f"/api/v1/manufacturing/cost-rollup/?product={fg.pk}").status_code == 200
    assert api.get(f"/api/v1/manufacturing/atp/?product={fg.pk}&date={due}").status_code == 200
    made = api.post("/api/v1/manufacturing/work-orders/from-sales-order/", {"sales_order": order.pk}, format="json")
    assert made.status_code == 201
    status_resp = api.get(f"/api/v1/manufacturing/sales-order-status/?sales_order={order.pk}")
    assert status_resp.status_code == 200
    wo_id = body(made)["created"][0]["id"]
    prio = api.post(f"/api/v1/manufacturing/work-orders/{wo_id}/set-priority/", {"priority": 1, "delay_reason": "CUSTOMER"}, format="json")
    assert prio.status_code == 200 and body(prio)["priority"] == 1
    assert api.post(f"/api/v1/manufacturing/work-orders/{wo_id}/set-priority/", {"priority": 9}, format="json").status_code == 400


def test_sales_staff_can_read_production_status_but_not_plan(tenant_a):
    c, fg, raw, order, due = mrp_world(tenant_a, "WAVG")
    planning_on(tenant_a)
    planning.create_orders_from_sales_order(order, tenant_a.owner)
    staff = tenant_a.staff_client
    assert staff.get(f"/api/v1/manufacturing/sales-order-status/?sales_order={order.pk}").status_code == 200
    assert staff.post("/api/v1/manufacturing/mrp-runs/run/", {}, format="json").status_code == 403
    assert staff.get("/api/v1/manufacturing/board/").status_code == 403
    _u, inv = member(tenant_a, "INVENTORY_STAFF", can_manage_inventory=True)
    assert inv.post("/api/v1/manufacturing/mrp-runs/run/", {}, format="json").status_code == 201
    run_id = body(inv.get("/api/v1/manufacturing/mrp-runs/"))[0]["id"]
    assert inv.post(f"/api/v1/manufacturing/mrp-runs/{run_id}/convert/", {}, format="json").status_code == 403    # converting is a manager's
