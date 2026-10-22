"""Block C of the test plan: Inventory Risk negative paths, repeat sweeps, roles, edits and scheduling."""
# ruff: noqa: F811  (pytest fixtures are imported from sibling test modules)

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from agents import runner, services
from agents.enums import ProposalStatus, RunStatus, Trigger
from agents.models import AgentProposal
from inventory.models import BatchLot, StockTransfer, Warehouse, WarehouseReorderLevel
from masters.models import Product, Supplier
from purchases.models import PurchaseOrder
from tests.conftest import make_product

from .test_inventory_risk import BASE, approve, d, iv, key, short_item, stock, sweep  # noqa: F401

pytestmark = pytest.mark.django_db


def transfer_and_purchase(iv_):
    short_item(iv_)
    drafts = {p.kind: p for p in AgentProposal.objects.filter(run=sweep(iv_))}
    return drafts["STOCK_TRANSFER"], drafts["PURCHASE_REQUEST"]


def edit(iv_, p, mutate):
    payload = json.loads(json.dumps(p.payload))
    mutate(payload)
    r = iv_.client.patch(f"{BASE}/proposals/{p.pk}/", {"editedPayload": payload, "revision": p.revision}, format="json")
    assert r.status_code == 200, r.content
    p.refresh_from_db()
    return p


# --- transfer executor negative paths ---------------------------------------------------------------------
def test_source_equal_to_destination_is_refused(iv):
    t, _ = transfer_and_purchase(iv)
    t = edit(iv, t, lambda pl: pl.update(to_warehouse_id=pl["from_warehouse_id"]))
    assert approve(iv, t).status_code == 400 and StockTransfer.objects.count() == 0


@pytest.mark.parametrize("field,change", [("is_active", False), ("is_system", True)])
def test_an_inactive_or_system_godown_makes_the_draft_stale(iv, field, change):
    t, _ = transfer_and_purchase(iv)
    Warehouse.objects.filter(pk=iv.north.pk).update(**{field: change})
    assert approve(iv, t).status_code == 409 and StockTransfer.objects.count() == 0


def test_a_missing_product_makes_the_draft_stale(iv):
    t, _ = transfer_and_purchase(iv)
    Product.objects.filter(pk=t.payload["lines"][0]["product_id"]).update(status="INACTIVE")
    assert approve(iv, t).status_code == 409


def test_a_lot_of_another_product_is_refused(iv):
    t, _ = transfer_and_purchase(iv)
    other = make_product(iv.company, name="Other", sku="OT1", track_batch=True)
    lot = BatchLot.objects.create(company=iv.company, product=other, batch_no="X1")
    t = edit(iv, t, lambda pl: pl["lines"][0].update(batch_id=lot.pk))
    assert approve(iv, t).status_code == 409 and StockTransfer.objects.count() == 0


def test_a_lot_that_expired_after_the_draft_is_refused(iv):
    milk = make_product(iv.company, sku="MK1", name="Milk", reorder_level="0", track_batch=True)
    lot = BatchLot.objects.create(company=iv.company, product=milk, batch_no="E1", expiry_date=timezone.localdate() + timedelta(days=30))
    stock(iv, milk, iv.main, "20", batch=lot)
    stock(iv, milk, iv.north, "1", batch=lot)
    WarehouseReorderLevel.objects.create(company=iv.company, warehouse=iv.north, product=milk, reorder_level=Decimal("10"))
    t = AgentProposal.objects.get(run=sweep(iv), kind="STOCK_TRANSFER")
    BatchLot.objects.filter(pk=lot.pk).update(expiry_date=timezone.localdate() - timedelta(days=1))
    assert approve(iv, t).status_code == 409


def test_one_thousandth_more_than_available_is_stale_and_exact_is_fine(iv):
    t, _ = transfer_and_purchase(iv)
    have = Decimal(t.payload["lines"][0]["qty"])
    ok = edit(iv, t, lambda pl: pl["lines"][0].update(qty=format(have, "f")))
    assert approve(iv, ok).status_code == 200
    t2 = AgentProposal.objects.filter(kind="STOCK_TRANSFER").first()
    assert t2.status == ProposalStatus.EXECUTED


def test_editing_to_more_than_the_donor_has_goes_stale(iv):
    t, _ = transfer_and_purchase(iv)
    t = edit(iv, t, lambda pl: pl["lines"][0].update(qty="9999"))
    r = approve(iv, t)
    t.refresh_from_db()
    assert r.status_code == 409 and t.failure_code == "STALE"


def test_an_edited_quantity_is_the_one_transferred(iv):
    t, _ = transfer_and_purchase(iv)
    t = edit(iv, t, lambda pl: pl["lines"][0].update(qty="1"))
    transfer = StockTransfer.objects.get(pk=d(approve(iv, t))["resultRef"]["id"])
    assert [l.quantity for l in transfer.lines.all()] == [Decimal("1.000")]


# --- purchase executor -------------------------------------------------------------------------------------------
def test_a_deleted_supplier_fails_cleanly(iv):
    _, p = transfer_and_purchase(iv)
    Supplier.objects.filter(pk=iv.supplier.pk).delete()
    assert approve(iv, p).status_code == 400 and PurchaseOrder.objects.count() == 0


def test_whole_unit_items_are_rounded_up(iv):
    _, p = transfer_and_purchase(iv)
    p = edit(iv, p, lambda pl: pl["lines"][0].update(qty="3.2"))
    po = PurchaseOrder.objects.get(pk=d(approve(iv, p))["resultRef"]["ids"][0])
    assert [i.quantity for i in po.items.all()] == [Decimal("4.000")]


def test_a_duplicate_draft_within_the_hour_fails_readably_and_stays_retryable(iv):
    rice = short_item(iv)
    broad = AgentProposal.objects.get(run=sweep(iv), kind="PURCHASE_REQUEST")
    row_run = runner.execute_run(services.create_run(
        company=iv.company, agent_kind="INVENTORY_RISK", trigger=Trigger.ATTENTION_ROW,
        trigger_ref=f"LOW_STOCK_FAST_MOVER:product:{rice.pk}", user=iv.owner).pk)
    narrow = AgentProposal.objects.get(run=row_run, kind="PURCHASE_REQUEST")
    assert broad.pk != narrow.pk  # two live drafts for the same item and supplier
    assert approve(iv, broad).status_code == 200
    r = approve(iv, narrow)
    assert r.status_code == 400 and "last hour" in json.dumps(r.json())
    narrow.refresh_from_db()
    assert narrow.status == ProposalStatus.FAILED and narrow.failure_code != "STALE"
    assert PurchaseOrder.objects.count() == 1


def test_two_lines_for_one_supplier_make_one_order(iv):
    short_item(iv, name="Rice", sku="RC1")
    short_item(iv, name="Dal", sku="DL1")
    run = sweep(iv)
    purchases = AgentProposal.objects.filter(run=run, kind="PURCHASE_REQUEST")
    assert purchases.count() == 1 and len(purchases[0].payload["lines"]) == 2
    d(approve(iv, purchases[0]))
    assert PurchaseOrder.objects.count() == 1 and PurchaseOrder.objects.get().items.count() == 2


# --- context ----------------------------------------------------------------------------------------------------------
def test_a_second_sweep_the_same_day_makes_no_duplicates(iv):
    short_item(iv)
    first = set(AgentProposal.objects.filter(run=sweep(iv)).values_list("pk", flat=True))
    sweep(iv)
    assert AgentProposal.objects.count() == len(first)


def test_an_item_covered_by_open_orders_is_not_drafted(iv):
    rice = short_item(iv, north_stock="2", main_stock=None)
    from purchases.models import PurchaseOrderItem

    order = PurchaseOrder.objects.create(company=iv.company, supplier=iv.supplier, created_by=iv.owner, updated_by=iv.owner)
    PurchaseOrderItem.objects.create(company=iv.company, purchase_order=order, product=rice, quantity=Decimal("50"), unit_price=Decimal("10"), gst_rate=Decimal("0"))
    run = sweep(iv)
    assert run.status == RunStatus.SUCCEEDED and not AgentProposal.objects.filter(run=run, kind="PURCHASE_REQUEST").exists()


def test_an_item_with_no_supplier_gets_a_note_not_a_purchase_draft(iv, monkeypatch):
    monkeypatch.setattr("inventory.reorder_maps.last_completed_suppliers", lambda company, ids: {})
    short_item(iv, north_stock="2", main_stock=None)
    run = sweep(iv)
    assert run.status == RunStatus.SUCCEEDED and not AgentProposal.objects.filter(run=run, kind="PURCHASE_REQUEST").exists()
    [note] = AgentProposal.objects.filter(run=run, kind="PURCHASE_NEEDS_SUPPLIER")
    assert note.payload["lines"][0]["item"] == "Rice"
    r = approve(iv, note)
    assert r.status_code == 200 and d(r)["resultRef"]["type"] == "acknowledged"
    assert PurchaseOrder.objects.count() == 0


def test_a_long_list_becomes_several_drafts_of_at_most_100_lines(iv):
    from masters.models import Product

    rows = Product.objects.bulk_create([
        Product(company=iv.company, name=f"Bulk {i}", sku=f"BK{i}", selling_price=Decimal("10"), gst_rate=Decimal("5"), reorder_level=Decimal("10"))
        for i in range(230)
    ])
    for p in rows:
        stock(iv, p, iv.main, "1")
    run = sweep(iv)
    purchases = AgentProposal.objects.filter(run=run, kind="PURCHASE_REQUEST").order_by("dedupe_key")
    assert run.status == RunStatus.SUCCEEDED and purchases.count() == 3
    assert sorted(len(p.payload["lines"]) for p in purchases) == [30, 100, 100]
    assert len({p.dedupe_key for p in purchases}) == 3


def test_a_quarantine_godown_destination_is_skipped(iv):
    quarantine = Warehouse.objects.create(company=iv.company, name="Hold bay", code="QB", kind="QUARANTINE")
    rice = make_product(iv.company, sku="RQ1", name="Rice", reorder_level="0")
    stock(iv, rice, iv.main, "40")
    stock(iv, rice, quarantine, "1")
    WarehouseReorderLevel.objects.create(company=iv.company, warehouse=quarantine, product=rice, reorder_level=Decimal("8"))
    assert not AgentProposal.objects.filter(run=sweep(iv), kind="STOCK_TRANSFER").exists()


def test_only_the_usable_part_of_a_batch_item_is_suggested(iv):
    milk = make_product(iv.company, sku="MK2", name="Milk", reorder_level="0", track_batch=True)
    good = BatchLot.objects.create(company=iv.company, product=milk, batch_no="G", expiry_date=timezone.localdate() + timedelta(days=60))
    old = BatchLot.objects.create(company=iv.company, product=milk, batch_no="O", expiry_date=timezone.localdate() - timedelta(days=2))
    stock(iv, milk, iv.main, "3", batch=good)
    stock(iv, milk, iv.main, "50", batch=old)
    stock(iv, milk, iv.north, "1", batch=good)
    WarehouseReorderLevel.objects.create(company=iv.company, warehouse=iv.north, product=milk, reorder_level=Decimal("10"))
    t = AgentProposal.objects.get(run=sweep(iv), kind="STOCK_TRANSFER")
    assert {l["batch_no"] for l in t.payload["lines"]} == {"G"} and sum(Decimal(l["qty"]) for l in t.payload["lines"]) <= Decimal("3")


# --- roles ------------------------------------------------------------------------------------------------------------
def test_a_user_with_neither_right_cannot_start_the_agent(iv):
    r = iv.staff_client.post(f"{BASE}/runs/", {"agent": "INVENTORY_RISK"}, format="json", **key())
    assert r.status_code in (400, 403)


def test_an_inventory_only_user_can_approve_the_transfer_but_not_the_purchase(iv):
    from accounts.models import CompanyUser

    t, p = transfer_and_purchase(iv)
    cu = CompanyUser.objects.get(company=iv.company, user=iv.staff)
    cu.can_manage_inventory = True
    cu.save()
    assert iv.staff_client.post(f"{BASE}/proposals/{p.pk}/approve/", {"revision": 0}, format="json", **key()).status_code in (404, 409)
    assert iv.staff_client.post(f"{BASE}/proposals/{t.pk}/approve/", {"revision": t.revision}, format="json", **key()).status_code == 200


# --- scheduling -----------------------------------------------------------------------------------------------------------
def test_the_scheduled_run_is_skipped_when_planning_is_off(iv):
    from agents import tasks

    flags = {k: v for k, v in iv.company.feature_flags.items() if k != "ENABLE_PURCHASE_PLANNING"}
    iv.company.feature_flags = flags
    iv.company.save(update_fields=["feature_flags"])
    short_item(iv)
    before = AgentProposal.objects.count()
    tasks.run_scheduled_agent_company("INVENTORY_RISK", company_id=iv.company.pk)
    assert AgentProposal.objects.count() == before
