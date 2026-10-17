"""INV-IDR-14 - the inventory paths that must hold when two people (or one double click) hit them at once.

SQLite does not enforce row locks, so these run only against PostgreSQL (CI with DATABASE_URL):
double dispatch, double receive, count post against cancel, two counters saving the same line, two
manual serial returns, double expiry write-off, double planning create.
"""

from __future__ import annotations

import threading
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import connection
from rest_framework.test import APIClient

from inventory.models import (
    BatchLot,
    SerialNumber,
    StockBalance,
    StockCountSession,
    StockMovement,
    StockTransfer,
    Warehouse,
)
from inventory.services import InventoryService, StockTransferService
from masters.models import Supplier
from purchases.models import PurchaseOrder
from tests.conftest import add_stock, make_product

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.postgres]

TRANSFERS = "/api/v1/inventory/transfers/"
COUNTS = "/api/v1/inventory/stock-counts/"


def _require_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row-level locking (select_for_update)")


def _race(tenant, calls):
    """Run each call(client) at the same instant on its own thread and connection; return the results."""
    barrier = threading.Barrier(len(calls), timeout=15)
    results: list = [None] * len(calls)

    def runner(index, call):
        connection.close()
        client = APIClient()
        client.force_authenticate(user=tenant.owner)
        try:
            barrier.wait()
            results[index] = call(client)
        except Exception as exc:  # pragma: no cover - reported by the assertion that follows
            results[index] = exc
        finally:
            connection.close()

    threads = [threading.Thread(target=runner, args=(i, c)) for i, c in enumerate(calls)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return results


def _statuses(results):
    return sorted(getattr(r, "status_code", -1) for r in results)


def _on_hand(company, product, warehouse):
    row = StockBalance.objects.filter(company=company, product=product, warehouse=warehouse, batch__isnull=True).first()
    return row.on_hand if row else Decimal("0")


def _godowns(tenant):
    main = InventoryService.default_warehouse(tenant.company)
    north = Warehouse.objects.create(company=tenant.company, name="North", code="C14")
    return main, north


def _draft_transfer(tenant, product, main, north, qty="4"):
    resp = tenant.client.post(
        TRANSFERS,
        {"from_warehouse": main.id, "to_warehouse": north.id, "lines": [{"product": product.id, "quantity": qty}]},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    return resp.data


def test_two_dispatches_of_one_transfer_move_the_stock_once(tenant_a):
    _require_postgres()
    main, north = _godowns(tenant_a)
    product = make_product(tenant_a.company, sku="C14-1")
    add_stock(tenant_a, product, "10")
    transfer = _draft_transfer(tenant_a, product, main, north)
    url = f"{TRANSFERS}{transfer['id']}/complete/"
    results = _race(tenant_a, [
        lambda c: c.post(url, {}, format="json", HTTP_IDEMPOTENCY_KEY="c14-d1"),
        lambda c: c.post(url, {}, format="json", HTTP_IDEMPOTENCY_KEY="c14-d2"),
    ])
    assert 200 in _statuses(results), results
    assert _on_hand(tenant_a.company, product, main) == Decimal("6")
    transit = StockTransferService.in_transit_warehouse(tenant_a.company)
    assert _on_hand(tenant_a.company, product, transit) == Decimal("4")
    assert StockTransfer.objects.get(pk=transfer["id"]).status == StockTransfer.Status.DISPATCHED


def test_two_receipts_of_one_transfer_land_the_stock_once(tenant_a):
    _require_postgres()
    main, north = _godowns(tenant_a)
    product = make_product(tenant_a.company, sku="C14-2")
    add_stock(tenant_a, product, "10")
    transfer = _draft_transfer(tenant_a, product, main, north)
    assert tenant_a.client.post(f"{TRANSFERS}{transfer['id']}/complete/", {}, format="json").status_code == 200
    url = f"{TRANSFERS}{transfer['id']}/receive/"
    results = _race(tenant_a, [
        lambda c: c.post(url, {}, format="json", HTTP_IDEMPOTENCY_KEY="c14-r1"),
        lambda c: c.post(url, {}, format="json", HTTP_IDEMPOTENCY_KEY="c14-r2"),
    ])
    assert 200 in _statuses(results), results
    assert _on_hand(tenant_a.company, product, north) == Decimal("4")
    transit = StockTransferService.in_transit_warehouse(tenant_a.company)
    assert _on_hand(tenant_a.company, product, transit) == Decimal("0")


def _counted_session(tenant, product, qty):
    main = InventoryService.default_warehouse(tenant.company)
    session = tenant.client.post(COUNTS, {"warehouse": main.id}, format="json").data
    line = next(row for row in session["lines"] if row["product"] == product.id)
    tenant.client.patch(
        f"{COUNTS}{session['id']}/", {"lines": [{"id": line["id"], "counted_qty": str(qty)}]}, format="json",
    )
    return session["id"], line["id"]


def test_posting_a_count_against_cancelling_it_ends_in_exactly_one_state(tenant_a):
    _require_postgres()
    product = make_product(tenant_a.company, sku="C14-3")
    add_stock(tenant_a, product, "10")
    session_id, line_id = _counted_session(tenant_a, product, 7)
    main = InventoryService.default_warehouse(tenant_a.company)
    results = _race(tenant_a, [
        lambda c: c.post(f"{COUNTS}{session_id}/post/", {"rechecked_line_ids": [line_id]}, format="json",
                         HTTP_IDEMPOTENCY_KEY="c14-p1"),
        lambda c: c.post(f"{COUNTS}{session_id}/cancel/", {}, format="json"),
    ])
    session = StockCountSession.objects.get(pk=session_id)
    on_hand = _on_hand(tenant_a.company, product, main)
    if session.status == StockCountSession.Status.POSTED:
        assert on_hand == Decimal("7"), (session.status, on_hand, results)
    else:
        assert session.status == StockCountSession.Status.CANCELLED
        assert on_hand == Decimal("10"), (session.status, on_hand, results)


def test_two_counters_saving_the_same_line_do_not_overwrite_each_other(tenant_a):
    _require_postgres()
    product = make_product(tenant_a.company, sku="C14-4")
    add_stock(tenant_a, product, "10")
    session_id, line_id = _counted_session(tenant_a, product, 9)
    line = tenant_a.client.get(f"{COUNTS}{session_id}/").data["lines"][0]
    body = lambda qty: {"lines": [{"id": line_id, "counted_qty": str(qty), "version": line["version"]}]}  # noqa: E731
    results = _race(tenant_a, [
        lambda c: c.patch(f"{COUNTS}{session_id}/", body(3), format="json"),
        lambda c: c.patch(f"{COUNTS}{session_id}/", body(4), format="json"),
    ])
    assert _statuses(results) == [200, 409], results
    assert any(r.data["error"]["code"] == "STOCK_COUNT_LINE_CHANGED" for r in results if r.status_code == 409)


def test_two_manual_returns_of_one_sold_unit_put_it_back_once(tenant_a):
    _require_postgres()
    product = make_product(tenant_a.company, sku="C14-5", track_serial=True)
    main = InventoryService.default_warehouse(tenant_a.company)
    serial = SerialNumber.objects.create(
        company=tenant_a.company, product=product, warehouse=main, serial_number="C14-SN",
        status=SerialNumber.Status.SOLD,
    )
    url = f"/api/v1/inventory/serials/{serial.pk}/transition/"
    body = {"status": "AVAILABLE", "reason": "Customer brought it back", "confirm_no_document": True}
    results = _race(tenant_a, [
        lambda c: c.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY="c14-s1"),
        lambda c: c.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY="c14-s2"),
    ])
    assert 200 in _statuses(results), results
    assert StockMovement.objects.filter(
        company=tenant_a.company, reference_type="serial_manual_return", reference_id=str(serial.pk),
    ).count() == 1


def test_two_write_offs_of_a_whole_lot_never_take_more_than_the_lot_holds(tenant_a):
    _require_postgres()
    product = make_product(tenant_a.company, sku="C14-6", track_batch=True, purchase_price="30")
    InventoryService.post_opening(
        company=tenant_a.company, product=product, quantity=Decimal("10"), unit_cost=Decimal("20"),
        batch_no="C14-L1", expiry_date=date.today() + timedelta(days=30), user=tenant_a.owner,
    )
    balance = StockBalance.objects.get(company=tenant_a.company, product=product)
    BatchLot.objects.filter(pk=balance.batch_id).update(expiry_date=date.today() - timedelta(days=3))
    body = {
        "product": product.id, "warehouse": balance.warehouse_id, "batch": balance.batch_id,
        "quantity": "10", "reason": "EXPIRED",
    }
    results = _race(tenant_a, [
        lambda c: c.post("/api/v1/inventory/alerts/expiry/", body, format="json", HTTP_IDEMPOTENCY_KEY="c14-e1"),
        lambda c: c.post("/api/v1/inventory/alerts/expiry/", body, format="json", HTTP_IDEMPOTENCY_KEY="c14-e2"),
    ])
    assert _statuses(results) == [201, 400], results
    assert StockBalance.objects.get(pk=balance.pk).on_hand == Decimal("0")
    assert StockMovement.objects.filter(
        company=tenant_a.company, product=product, reference_type="expiry_write_off",
    ).count() == 1


def test_two_planning_creates_with_the_same_key_make_one_set_of_drafts(tenant_a):
    _require_postgres()
    tenant_a.company.feature_flags = {"ENABLE_PURCHASE_PLANNING": True, "ENABLE_REPLENISHMENT": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    supplier = Supplier.objects.create(company=tenant_a.company, name="Mega", state="Karnataka")
    product = make_product(tenant_a.company, sku="C14-7", reorder_level="10")
    body = {"rows": [{"product_id": product.id, "suggested_qty": "4", "supplier_id": supplier.id}]}
    results = _race(tenant_a, [
        lambda c: c.post("/api/v1/inventory/purchase-planning/", body, format="json", HTTP_IDEMPOTENCY_KEY="c14-pl"),
        lambda c: c.post("/api/v1/inventory/purchase-planning/", body, format="json", HTTP_IDEMPOTENCY_KEY="c14-pl"),
    ])
    assert 200 in _statuses(results), results
    assert PurchaseOrder.objects.filter(company=tenant_a.company).count() == 1


def test_the_inventory_ledger_still_adds_up_after_the_races(tenant_a):
    """The balance of every item equals the sum of its movements (the invariant the suite checks)."""
    _require_postgres()
    main, north = _godowns(tenant_a)
    product = make_product(tenant_a.company, sku="C14-8")
    add_stock(tenant_a, product, "20")
    transfer = _draft_transfer(tenant_a, product, main, north, qty="5")
    url = f"{TRANSFERS}{transfer['id']}/complete/"
    _race(tenant_a, [lambda c: c.post(url, {}, format="json") for _ in range(3)])
    for balance in StockBalance.objects.filter(company=tenant_a.company, product=product):
        moved = sum(
            (m.quantity for m in StockMovement.objects.filter(
                company=tenant_a.company, product=product, warehouse=balance.warehouse, batch=balance.batch,
            )),
            Decimal("0"),
        )
        assert balance.on_hand == moved, (balance.warehouse_id, balance.on_hand, moved)
