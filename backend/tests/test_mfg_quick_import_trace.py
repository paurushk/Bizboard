"""Quick production entry, recipe import/export, genealogy queries, backup round trip."""

import io
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.invariants import assert_all_invariants
from inventory.models import BatchLot, MovementType, StockBalance
from inventory.services import InventoryService
from manufacturing.models import Bom, MaterialIssue, ProductionReceipt, WorkOrder
from manufacturing.services import quick_entry, trace
from manufacturing.services import bom_import
from tests.conftest import make_product, make_tenant
from tests.mfg_helpers import account_net, body, make_bom, make_wo, member, prepare, stocked

pytestmark = pytest.mark.django_db


@pytest.fixture(params=["WAVG", "FIFO"])
def method(request):
    return request.param


def D(v):
    return Decimal(str(v))


# --- quick entry ------------------------------------------------------------------------------

def test_quick_production_posts_the_same_books_as_the_long_path(method):
    """The one-screen path and the step-by-step path must leave identical stock, cost and journals."""
    from manufacturing.services import flow, issue as issue_svc, receipt as receipt_svc, release_work_order

    results = []
    for slug, quick in (("quickco", True), ("longco", False)):
        tenant = make_tenant(slug)
        company = prepare(tenant, method=method)
        fg = make_product(company, sku="G-FG")
        comp = stocked(tenant, "G-COMP", 500, 12)
        bom = make_bom(company, fg, [(comp, 2)], user=tenant.owner)
        if quick:
            wo = quick_entry.quick_production(company, tenant.owner, product=fg, qty=30)
        else:
            wo = release_work_order(make_wo(company, bom, 30, user=tenant.owner), tenant.owner)
            wl = wo.component_lines.get()
            issue_svc.post_issue(issue_svc.create_issue(wo, tenant.owner, [{"wo_line": wl, "qty": wl.qty}]), tenant.owner)
            receipt_svc.post_receipt(receipt_svc.create_receipt(wo, tenant.owner, {"is_final": True}), tenant.owner)
            wo = flow.close_work_order(wo, tenant.owner)
        results.append({
            "status": wo.status,
            "issued": wo.cost_issued, "received": wo.cost_received, "wip": wo.wip_value,
            "comp": StockBalance.objects.get(company=company, product=comp).on_hand,
            "fg": StockBalance.objects.get(company=company, product=fg).on_hand,
            "g1450": account_net(company, "1450"), "g1400": account_net(company, "1400"),
        })
        assert_all_invariants(company)
    assert results[0] == results[1]
    assert results[0]["status"] == "CLOSED" and results[0]["fg"] == D(30) and results[0]["comp"] == D(440)


def test_quick_production_uses_actual_quantities_and_marks_extra_use(tenant_a, method):
    company = prepare(tenant_a, method=method)
    fg = make_product(company, sku="QA-FG")
    comp = stocked(tenant_a, "QA-COMP", 500, 10)
    make_bom(company, fg, [(comp, 1)], user=tenant_a.owner)
    wo = quick_entry.quick_production(
        company, tenant_a.owner, product=fg, qty=100, components={comp: 104}, is_manager=False,
    )
    assert wo.cost_issued == D("1040.00") and wo.cost_received == D("1040.00")
    issue = MaterialIssue.objects.get(work_order=wo)
    assert issue.lines.get().is_extra and "quick" in issue.lines.get().extra_reason.lower()
    usage = wo.variances.get(kind="USAGE")
    assert usage.variance == D("40.00")


def test_quick_production_is_all_or_nothing(tenant_a, method):
    company = prepare(tenant_a, method=method)
    fg = make_product(company, sku="QN-FG")
    comp = stocked(tenant_a, "QN-COMP", 5, 10)                  # not enough for 20 units
    make_bom(company, fg, [(comp, 1)], user=tenant_a.owner)
    before_numbers = WorkOrder.objects.count()
    with pytest.raises(BusinessRuleError):
        quick_entry.quick_production(company, tenant_a.owner, product=fg, qty=20)
    assert WorkOrder.objects.count() == before_numbers
    assert not MaterialIssue.objects.exists() and not ProductionReceipt.objects.exists()
    assert StockBalance.objects.get(company=company, product=comp).on_hand == D(5)


def test_quick_production_with_planned_by_product_and_batch(tenant_a, method):
    company = prepare(tenant_a, method=method)
    fg = make_product(company, sku="QB-FG", track_batch=True)
    by = make_product(company, sku="QB-BY", name="Stalk")
    comp = stocked(tenant_a, "QB-COMP", 500, 10)
    make_bom(
        company, fg, [(comp, 100)], user=tenant_a.owner, output_qty="100",
        outputs=[{"product": by, "kind": "BY_PRODUCT", "qty": D("3"), "recovery_rate": D("4")}],
    )
    exp = timezone.localdate() + timedelta(days=200)
    wo = quick_entry.quick_production(
        company, tenant_a.owner, product=fg, qty=200, batch_no="CP-0042", exp_date=exp,
    )
    assert BatchLot.objects.get(company=company, product=fg, batch_no="CP-0042").expiry_date == exp
    assert StockBalance.objects.get(company=company, product=by).on_hand == D(6)
    assert wo.cost_received == wo.cost_issued                      # by-product value is part of what came out
    assert_all_invariants(company)


def test_quick_production_api_needs_no_manager_for_a_normal_run(tenant_a):
    company = prepare(tenant_a, method="WAVG", separate=False)       # works whichever mode the company uses
    fg = make_product(company, sku="QP-FG")
    comp = stocked(tenant_a, "QP-COMP", 100, 10)
    make_bom(company, fg, [(comp, 1)], user=tenant_a.owner)
    _u, inv = member(tenant_a, "INVENTORY_STAFF", can_manage_inventory=True)
    resp = inv.post(
        "/api/v1/manufacturing/quick-production/", {"product": fg.id, "qty": "10"}, format="json",
        HTTP_IDEMPOTENCY_KEY="q1",
    )
    assert resp.status_code == 201, resp.data
    assert body(resp)["status"] == "CLOSED"
    again = inv.post(
        "/api/v1/manufacturing/quick-production/", {"product": fg.id, "qty": "10"}, format="json",
        HTTP_IDEMPOTENCY_KEY="q1",
    )
    assert again.status_code in (200, 201)
    assert WorkOrder.objects.filter(company=company).count() == 1                # the retry did not make a second one
    assert StockBalance.objects.get(company=company, product=fg).on_hand == D(10)
    # A viewer cannot.
    _v, viewer = member(tenant_a, "VIEWER")
    assert viewer.post("/api/v1/manufacturing/quick-production/", {"product": fg.id, "qty": "1"}, format="json").status_code == 403


def test_quick_production_with_no_active_recipe_says_so(tenant_a):
    company = prepare(tenant_a)
    fg = make_product(company, sku="QX-FG")
    with pytest.raises(BusinessRuleError) as exc:
        quick_entry.quick_production(company, tenant_a.owner, product=fg, qty=1)
    assert exc.value.get_codes() == "MFG_NO_ACTIVE_BOM"


# --- import and export ------------------------------------------------------------------------

CSV_OK = (
    "row_type,finished_sku,bom_name,output_qty,yield_pct,item_sku,qty,unit,scrap_pct,issue_method,kind,cost_share_pct,recovery_rate\n"
    "LINE,IMP-FG,Imp recipe,100,98,IMP-A,62,,2,MANUAL,,,\n"
    "LINE,IMP-FG,Imp recipe,100,98,IMP-B,100,,0,BACKFLUSH,,,\n"
    "OUTPUT,IMP-FG,Imp recipe,100,98,IMP-BY,3,,,,BY_PRODUCT,0,4\n"
)


def _imp_products(tenant):
    c = tenant.company
    return (
        make_product(c, sku="IMP-FG"), make_product(c, sku="IMP-A"), make_product(c, sku="IMP-B"),
        make_product(c, sku="IMP-BY"),
    )


def test_import_dry_run_then_commit_makes_an_active_revision(tenant_a):
    _imp_products(tenant_a)
    c = tenant_a.client
    f = lambda: SimpleUploadedFile("boms.csv", CSV_OK.encode(), content_type="text/csv")      # noqa: E731
    dry = c.post("/api/v1/manufacturing/boms/import/", {"file": f()}, format="multipart")
    assert dry.status_code == 200 and not body(dry)["committed"] and body(dry)["recipes"][0]["materials"] == 2
    assert not Bom.objects.exists()
    done = c.post("/api/v1/manufacturing/boms/import/", {"file": f(), "commit": "true"}, format="multipart")
    assert done.status_code == 201 and body(done)["created"] == 1
    bom = Bom.objects.get()
    assert bom.status == "ACTIVE" and bom.is_default and bom.output_qty == D(100) and bom.yield_pct == D(98)
    assert bom.lines.get(component__sku="IMP-B").issue_method == "BACKFLUSH"
    assert bom.outputs.get().recovery_rate == D(4)
    # Importing again makes revision 2 and moves the default.
    c.post("/api/v1/manufacturing/boms/import/", {"file": f(), "commit": "true"}, format="multipart")
    assert sorted(Bom.objects.values_list("revision_no", flat=True)) == [1, 2]
    assert Bom.objects.get(is_default=True).revision_no == 2


def test_import_is_all_or_nothing_and_names_the_bad_rows(tenant_a):
    _imp_products(tenant_a)
    bad = CSV_OK + "LINE,IMP-FG,Imp recipe,100,98,NOPE,5,,0,MANUAL,,,\nLINE,IMP-FG,Imp recipe,100,98,IMP-A,abc,,0,MANUAL,,,\n"
    resp = tenant_a.client.post(
        "/api/v1/manufacturing/boms/import/",
        {"file": SimpleUploadedFile("b.csv", bad.encode()), "commit": "true"}, format="multipart",
    )
    assert resp.status_code == 422
    msgs = {e["row"]: e["message"] for e in body(resp)["errors"]}
    assert "NOPE" in msgs[5] and "number" in msgs[6]
    assert not Bom.objects.exists()


def test_import_refuses_a_recipe_that_contains_itself(tenant_a):
    fg, a, _b, _by = _imp_products(tenant_a)
    csv_text = "row_type,finished_sku,bom_name,item_sku,qty\nLINE,IMP-FG,Loop,IMP-FG,1\n"
    rows = bom_import.parse_file(SimpleUploadedFile("loop.csv", csv_text.encode()))
    result = bom_import.run_import(tenant_a.company, tenant_a.owner, rows, commit=True)
    assert result["errors"] and "finished good" in result["errors"][0]["message"]


def test_import_needs_the_right_columns_and_role(tenant_a):
    _imp_products(tenant_a)
    resp = tenant_a.client.post(
        "/api/v1/manufacturing/boms/import/", {"file": SimpleUploadedFile("x.csv", b"a,b\n1,2\n")}, format="multipart",
    )
    assert resp.status_code == 400 and "MFG_IMPORT_COLUMNS" in str(resp.data)
    _u, inv = member(tenant_a, "INVENTORY_STAFF", can_manage_inventory=True)
    denied = inv.post("/api/v1/manufacturing/boms/import/", {"file": SimpleUploadedFile("b.csv", CSV_OK.encode())}, format="multipart")
    assert denied.status_code == 403


def test_xlsx_import_and_export_round_trip(tenant_a):
    from openpyxl import Workbook

    _imp_products(tenant_a)
    wb = Workbook()
    ws = wb.active
    for line in CSV_OK.strip().split("\n"):
        ws.append(line.split(","))
    buf = io.BytesIO()
    wb.save(buf)
    up = SimpleUploadedFile("boms.xlsx", buf.getvalue())
    rows = bom_import.parse_file(up)
    assert bom_import.run_import(tenant_a.company, tenant_a.owner, rows, commit=True)["created"] == 1
    exported = bom_import.export_csv(tenant_a.company)
    assert "IMP-A" in exported and "BY_PRODUCT" in exported
    # What went out can come straight back in as the next revision.
    again = bom_import.parse_file(SimpleUploadedFile("out.csv", exported.encode()))
    result = bom_import.run_import(tenant_a.company, tenant_a.owner, again, commit=True)
    assert result["created"] == 1 and result["errors"] == []
    assert tenant_a.client.get("/api/v1/manufacturing/boms/export/").status_code == 200
    assert tenant_a.client.get("/api/v1/manufacturing/boms/import-template/").status_code == 200


# --- genealogy --------------------------------------------------------------------------------

def test_trace_back_and_forward_across_two_levels(tenant_a, method):

    company = prepare(tenant_a, method=method)
    raw = make_product(company, sku="T-RAW", track_batch=True, purchase_price="5")
    semi = make_product(company, sku="T-SEMI", track_batch=True)
    fg = make_product(company, sku="T-FG", track_batch=True)
    exp = timezone.localdate() + timedelta(days=300)
    raw_lot = BatchLot.objects.create(company=company, product=raw, batch_no="SUP-1", expiry_date=exp)
    InventoryService.post_movement(
        company=company, product=raw, batch=raw_lot, movement_type=MovementType.PURCHASE, quantity=D(200),
        unit_cost=D(5), user=tenant_a.owner, reference_type="purchase_invoice", reference_id="999",
    )
    make_bom(company, semi, [(raw, 2)], user=tenant_a.owner, name="semi")
    make_bom(company, fg, [(semi, 1)], user=tenant_a.owner, name="fg")
    quick_entry.quick_production(company, tenant_a.owner, product=semi, qty=50, batch_no="SEMI-1", exp_date=exp)
    quick_entry.quick_production(company, tenant_a.owner, product=fg, qty=20, batch_no="FG-1", exp_date=exp)
    fg_lot = BatchLot.objects.get(company=company, product=fg, batch_no="FG-1")
    back = trace.trace_back(company, fg_lot)
    names = {(n["depth"], n["batch"]) for n in back}
    assert (1, "SEMI-1") in names and (2, "SUP-1") in names
    forward = trace.trace_forward(company, raw_lot)
    assert {(m["batch"], m["depth"]) for m in forward["made_from_it"]} >= {("SEMI-1", 1), ("FG-1", 2)}
    # The API answers the same question.
    resp = tenant_a.client.get(f"/api/v1/manufacturing/trace/?batch={fg_lot.pk}&direction=back")
    assert resp.status_code == 200 and len(body(resp)["inputs"]) >= 2
    fwd = tenant_a.client.get(f"/api/v1/manufacturing/trace/?batch={raw_lot.pk}&direction=forward")
    assert fwd.status_code == 200 and len(body(fwd)["made_from_it"]) >= 2
    assert tenant_a.client.get("/api/v1/manufacturing/trace/?batch=999999").status_code == 400


def test_a_reversed_document_drops_out_of_the_trace(tenant_a, method):
    from manufacturing.services import issue as issue_svc, release_work_order

    company = prepare(tenant_a, method=method)
    fg = make_product(company, sku="TR-FG", track_batch=True)
    raw = make_product(company, sku="TR-RAW", track_batch=True, purchase_price="4")
    lot = BatchLot.objects.create(company=company, product=raw, batch_no="R-1", expiry_date=timezone.localdate() + timedelta(days=90))
    InventoryService.post_movement(
        company=company, product=raw, batch=lot, movement_type=MovementType.PURCHASE, quantity=D(50), unit_cost=D(4),
        user=tenant_a.owner,
    )
    bom = make_bom(company, fg, [(raw, 1)], user=tenant_a.owner)
    wo = release_work_order(make_wo(company, bom, 10, user=tenant_a.owner), tenant_a.owner)
    wl = wo.component_lines.get()
    issue = issue_svc.post_issue(issue_svc.create_issue(wo, tenant_a.owner, [{"wo_line": wl, "qty": 10}]), tenant_a.owner)
    issue_svc.reverse_issue(issue, tenant_a.owner, "wrong lot")
    from inventory.models import TraceLink

    assert not TraceLink.objects.filter(company=company, reversed_at__isnull=True).exists()


# --- settings, godown defaults, backup --------------------------------------------------------

def test_role_godowns_decide_where_material_comes_from_and_output_goes(tenant_a, method):
    from inventory.models import Warehouse

    company = prepare(tenant_a, method=method)
    rm = Warehouse.objects.create(company=company, name="RM store", code="RM")
    fgw = Warehouse.objects.create(company=company, name="FG store", code="FG")
    cfg = prepare(tenant_a, method=method, rm_warehouse=rm, fg_warehouse=fgw)
    fg = make_product(company, sku="RG-FG", mfg_role="FINISHED")
    comp = make_product(company, sku="RG-COMP", mfg_role="RAW", purchase_price="10")
    InventoryService.post_movement(
        company=company, product=comp, warehouse=rm, movement_type=MovementType.PURCHASE, quantity=D(100),
        unit_cost=D(10), user=tenant_a.owner,
    )
    make_bom(company, fg, [(comp, 1)], user=tenant_a.owner)
    wo = quick_entry.quick_production(company, tenant_a.owner, product=fg, qty=10)
    assert StockBalance.objects.get(company=company, product=comp, warehouse=rm).on_hand == D(90)
    assert StockBalance.objects.get(company=company, product=fg, warehouse=fgw).on_hand == D(10)
    assert wo.status == "CLOSED"


@pytest.mark.django_db(transaction=True)
def test_backup_round_trip_keeps_recipes_orders_and_documents(tenant_a):
    from accounts.tenant_backup import build_export_payload, restore_destroy_in_place
    from manufacturing.models import MaterialIssueLine, ProductionReceiptLine

    company = prepare(tenant_a, method="WAVG")
    fg = make_product(company, sku="BK-FG")
    by = make_product(company, sku="BK-BY")
    comp = stocked(tenant_a, "BK-COMP", 300, 10)
    bom = make_bom(
        company, fg, [(comp, 1)], user=tenant_a.owner,
        outputs=[{"product": by, "kind": "BY_PRODUCT", "qty": D("0.1"), "recovery_rate": D("2")}],
    )
    quick_entry.quick_production(company, tenant_a.owner, product=fg, qty=50)
    wo = WorkOrder.objects.get()
    before = {
        "boms": Bom.objects.count(), "issues": MaterialIssueLine.objects.count(),
        "receipts": ProductionReceiptLine.objects.count(), "cost": wo.cost_received, "number": wo.number,
    }
    payload = build_export_payload(company)
    assert payload["mfg_material_issues"] and payload["mfg_production_receipts"] and payload["bom_outputs"]
    restore_destroy_in_place(
        company=company, payload=payload, owner=tenant_a.owner, confirm_destroy_unbacked=True,
    )
    wo2 = WorkOrder.objects.get(company=company)
    assert wo2.number == before["number"] and wo2.cost_received == before["cost"] and wo2.status == "CLOSED"
    assert Bom.objects.filter(company=company).count() == before["boms"]
    assert MaterialIssueLine.objects.filter(company=company).count() == before["issues"]
    assert ProductionReceiptLine.objects.filter(company=company).count() == before["receipts"]
    assert wo2.bom.outputs.get().kind == "BY_PRODUCT"
