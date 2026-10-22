"""Inventory Risk Agent (R4): drafts equal the planning rows, lots are safe, approval makes drafts only."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from agents import runner, services, spec
from agents.catalog import inventory_risk as inv_pkg
from agents.enums import ProposalStatus, RunStatus, Trigger
from agents.models import AgentProposal
from inventory.models import BatchLot, MovementType, StockBalance, StockTransfer, Warehouse, WarehouseReorderLevel
from inventory.planning import purchase_plan
from inventory.services import InventoryService
from masters.models import Supplier
from purchases.models import PurchaseOrder
from tests.conftest import make_product, make_tenant

from .conftest import enable_agents

import uuid

pytestmark = pytest.mark.django_db

BASE = "/api/v1/agents"


def key():
    return {"HTTP_IDEMPOTENCY_KEY": f"k-{uuid.uuid4()}"}


def d(resp):
    return resp.json()["data"]


@pytest.fixture
def iv(db, monkeypatch):
    added = "INVENTORY_RISK" not in spec.AGENTS
    if added:
        spec.register(inv_pkg.AGENT)
    t = make_tenant("iv1")
    enable_agents(t.company, "AGENT_INVENTORY_RISK")
    t.company.feature_flags = {**t.company.feature_flags, "ENABLE_PURCHASE_PLANNING": True, "ENABLE_REPLENISHMENT": True, "MFG_QUALITY": True}
    t.company.save(update_fields=["feature_flags"])
    t.main = InventoryService.default_warehouse(t.company)
    t.north = Warehouse.objects.create(company=t.company, name="North", code="NR")
    t.supplier = Supplier.objects.create(company=t.company, name="Mega Foods", state="Karnataka")
    monkeypatch.setattr("inventory.reorder_maps.last_completed_suppliers", lambda company, ids: {pid: t.supplier.id for pid in ids})
    yield t
    if added:
        spec.unregister("INVENTORY_RISK")


def stock(t, product, warehouse, qty, batch=None):
    InventoryService.post_movement(
        company=t.company, product=product, movement_type=MovementType.OPENING_STOCK, quantity=Decimal(qty),
        unit_cost=Decimal("10"), user=t.owner, warehouse=warehouse, batch=batch,
    )


def short_item(t, name="Rice", north_stock="2", main_stock="4", sku="RC1", **kw):
    """Short at North (own rule 8), main godown holds some stock: a split case when main has little surplus."""
    p = make_product(t.company, sku=sku, name=name, reorder_level="0", **kw)
    if north_stock:
        stock(t, p, t.north, north_stock)
    if main_stock:
        stock(t, p, t.main, main_stock)
    WarehouseReorderLevel.objects.create(company=t.company, warehouse=t.north, product=p, reorder_level=Decimal("8"))
    return p


def sweep(t):
    run = services.create_run(company=t.company, agent_kind="INVENTORY_RISK", trigger=Trigger.SCHEDULE, trigger_ref=f"sweep:{uuid.uuid4()}", user=t.owner)
    return runner.execute_run(run.pk)


def approve(t, p):
    return t.client.post(f"{BASE}/proposals/{p.pk}/approve/", {"revision": p.revision}, format="json", **key())


def test_a_split_shortage_becomes_two_linked_drafts_with_the_planning_quantities(iv):
    rice = short_item(iv)  # short 6 at North; main can give 4, so 2 are bought
    plan = {(r["transfer_from_warehouse_id"] is not None): Decimal(r["suggested_qty"]) for r in purchase_plan(iv.company)["rows"]}
    run = sweep(iv)
    assert run.status == RunStatus.SUCCEEDED and run.rules_only is True
    transfer = AgentProposal.objects.get(run=run, kind="STOCK_TRANSFER")
    purchase = AgentProposal.objects.get(run=run, kind="PURCHASE_REQUEST")
    assert Decimal(transfer.payload["lines"][0]["qty"]) == plan[True] == Decimal("4")
    assert Decimal(purchase.payload["lines"][0]["qty"]) == plan[False] == Decimal("2")
    assert transfer.group_key == purchase.group_key and transfer.group_key.startswith("INV:")
    assert transfer.dedupe_key != purchase.dedupe_key and purchase.payload["supplier_name"] == "Mega Foods"
    assert transfer.evidence and transfer.evidence[0]["id"] == rice.id


def test_approving_a_transfer_creates_a_draft_and_moves_no_stock(iv):
    short_item(iv)
    run = sweep(iv)
    p = AgentProposal.objects.get(run=run, kind="STOCK_TRANSFER")
    before = {(b.warehouse_id, b.product_id): (b.on_hand, b.reserved) for b in StockBalance.objects.filter(company=iv.company)}
    r = approve(iv, p)
    assert r.status_code == 200, r.content
    t = StockTransfer.objects.get(pk=d(r)["resultRef"]["id"])
    assert t.status == StockTransfer.Status.DRAFT and t.number and (t.from_warehouse, t.to_warehouse) == (iv.main, iv.north)
    assert [(l.quantity, l.batch_id) for l in t.lines.all()] == [(Decimal("4.000"), None)]
    after = {(b.warehouse_id, b.product_id): (b.on_hand, b.reserved) for b in StockBalance.objects.filter(company=iv.company)}
    assert after == before
    assert approve(iv, p).status_code == 409 and StockTransfer.objects.count() == 1


def test_approving_a_purchase_creates_a_draft_order_for_the_supplier(iv):
    short_item(iv)
    p = AgentProposal.objects.get(run=sweep(iv), kind="PURCHASE_REQUEST")
    r = approve(iv, p)
    assert r.status_code == 200, r.content
    po = PurchaseOrder.objects.get(company=iv.company)
    assert po.status == PurchaseOrder.Status.DRAFT and po.supplier_id == iv.supplier.id
    assert [i.quantity for i in po.items.all()] == [Decimal("2.000")]


@pytest.mark.invariant_skip("inventory.balance_equals_movements", reason="stock balances or movements are written directly through the ORM")
def test_a_transfer_goes_stale_if_the_donor_stock_is_gone(iv):
    rice = short_item(iv)
    p = AgentProposal.objects.get(run=sweep(iv), kind="STOCK_TRANSFER")
    stock_row = StockBalance.objects.get(company=iv.company, warehouse=iv.main, product=rice)
    StockBalance.objects.filter(pk=stock_row.pk).update(on_hand=Decimal("1"))
    r = approve(iv, p)
    assert r.status_code == 409 and StockTransfer.objects.count() == 0
    p.refresh_from_db()
    assert p.status == ProposalStatus.FAILED and p.failure_code == "STALE"


def test_expired_and_held_lots_are_never_suggested(iv):
    milk = make_product(iv.company, sku="ML1", name="Milk powder", reorder_level="0", track_batch=True)
    today = timezone.localdate()
    good = BatchLot.objects.create(company=iv.company, product=milk, batch_no="GOOD", expiry_date=today + timedelta(days=90))
    old = BatchLot.objects.create(company=iv.company, product=milk, batch_no="OLD", expiry_date=today - timedelta(days=5))
    held = BatchLot.objects.create(company=iv.company, product=milk, batch_no="HELD", expiry_date=today + timedelta(days=30), quality_status="HOLD")
    for lot in (old, held, good):
        stock(iv, milk, iv.main, "5", batch=lot)
    stock(iv, milk, iv.north, "1", batch=good)
    WarehouseReorderLevel.objects.create(company=iv.company, warehouse=iv.north, product=milk, reorder_level=Decimal("10"))
    run = sweep(iv)
    batches = {
        l["batch_no"]
        for p in AgentProposal.objects.filter(run=run, kind="STOCK_TRANSFER")
        for l in p.payload["lines"]
    }
    assert batches == {"GOOD"}
    assert "OLD" not in batches and "HELD" not in batches


def test_a_scrap_godown_is_never_a_donor(iv):
    rice = make_product(iv.company, sku="RC9", name="Rice", reorder_level="0")
    scrap = Warehouse.objects.create(company=iv.company, name="Scrap yard", code="SC", kind="SCRAP")
    stock(iv, rice, scrap, "50")
    stock(iv, rice, iv.north, "1")
    WarehouseReorderLevel.objects.create(company=iv.company, warehouse=iv.north, product=rice, reorder_level=Decimal("8"))
    run = sweep(iv)
    assert not AgentProposal.objects.filter(run=run, kind="STOCK_TRANSFER").exists()


def test_a_row_run_covers_only_that_item_and_groups_under_the_row(iv):
    rice = short_item(iv)
    short_item(iv, name="Dal", sku="DL1")
    ref = f"LOW_STOCK_FAST_MOVER:product:{rice.id}"
    run = runner.execute_run(services.create_run(company=iv.company, agent_kind="INVENTORY_RISK", trigger=Trigger.ATTENTION_ROW, trigger_ref=ref, user=iv.owner).pk)
    ps = list(AgentProposal.objects.filter(run=run))
    assert {p.kind for p in ps} == {"STOCK_TRANSFER", "PURCHASE_REQUEST"}
    assert all(p.group_key == ref and p.payload["lines"][0]["product_id"] == rice.id for p in ps)


def test_nothing_low_means_a_quiet_sweep_and_a_row_with_nothing_fails_clearly(iv):
    run = sweep(iv)
    assert run.status == RunStatus.SUCCEEDED and not AgentProposal.objects.filter(run=run).exists()
    ref = "LOW_STOCK_FAST_MOVER:product:999"
    bad = runner.execute_run(services.create_run(company=iv.company, agent_kind="INVENTORY_RISK", trigger=Trigger.ATTENTION_ROW, trigger_ref=ref, user=iv.owner).pk)
    assert bad.status == RunStatus.FAILED


def test_the_agent_needs_purchase_planning_switched_on(iv):
    iv.company.feature_flags = {k: v for k, v in iv.company.feature_flags.items() if k != "ENABLE_PURCHASE_PLANNING"}
    iv.company.save(update_fields=["feature_flags"])
    r = iv.client.post(f"{BASE}/runs/", {"agent": "INVENTORY_RISK"}, format="json", **key())
    assert r.status_code == 403
