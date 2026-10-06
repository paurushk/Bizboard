"""Race / duplicate scenarios the issue register lists as having no test.

Same pattern as test_concurrency_races.py: real threads released together by a
``threading.Barrier`` against PostgreSQL (row locks are meaningless on SQLite).
"""

from __future__ import annotations

import threading
from decimal import Decimal

import pytest
from django.db import connection
from rest_framework.test import APIClient

from core.exceptions import BusinessRuleError
from inventory.models import (
    MovementType,
    StockBalance,
    StockMovement,
    StockTransfer,
    StockTransferLine,
    Warehouse,
)
from inventory.services import InventoryService, StockTransferService
from tests.conftest import add_stock, make_customer, make_product, make_supplier

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.postgres]

PERIOD = "2026-04"


def _require_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row-level locking (select_for_update)")


def _run_concurrently(work, n=2):
    """Run ``work(i)`` in ``n`` threads released together. Returns (results, errors)."""
    results: list = []
    errors: list = []
    barrier = threading.Barrier(n, timeout=10)

    def runner(i):
        connection.close()
        try:
            barrier.wait()
            results.append(work(i))
        except Exception as exc:  # collected and asserted by the caller
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=runner, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results, errors


def test_concurrent_stock_transfers_cannot_overdraw_source(tenant_a):
    """Two transfers of the full on-hand qty out of one warehouse -> exactly one wins.

    StockTransferService.complete posts TRANSFER_OUT through post_movement, which
    re-checks availability under the balance row lock (policy BLOCK).
    """
    _require_postgres()
    company = tenant_a.company
    company.negative_stock_policy = "BLOCK"
    company.save(update_fields=["negative_stock_policy"])
    product = make_product(company, sku="RACE-XFER")
    source = InventoryService.default_warehouse(company)
    dest = Warehouse.objects.create(company=company, name="Branch", code="BR-RACE")
    add_stock(tenant_a, product, "5")

    transfers = []
    for _ in range(2):
        t = StockTransfer.objects.create(
            company=company, from_warehouse=source, to_warehouse=dest,
        )
        StockTransferLine.objects.create(transfer=t, product=product, quantity=Decimal("5"))
        transfers.append(t)

    def work(i):
        return StockTransferService.complete(transfers[i], tenant_a.owner)

    results, errors = _run_concurrently(work)

    assert len(results) == 1, (results, errors)
    assert len(errors) == 1 and isinstance(errors[0], BusinessRuleError), errors
    assert StockBalance.objects.get(company=company, warehouse=source, product=product).on_hand == Decimal("0")
    # complete() now only dispatches: the stock sits in transit until the destination receives it.
    assert sorted(StockTransfer.objects.values_list("status", flat=True)) == ["DISPATCHED", "DRAFT"]
    winner = StockTransfer.objects.get(status="DISPATCHED")
    StockTransferService.receive(winner, tenant_a.owner)
    assert StockBalance.objects.get(company=company, warehouse=dest, product=product).on_hand == Decimal("5")
    assert sorted(StockTransfer.objects.values_list("status", flat=True)) == ["COMPLETED", "DRAFT"]
    # Dispatch moves source → transit (TRANSFER_OUT). Receive moves transit →
    # destination (a second TRANSFER_OUT). The loser never posts.
    assert StockMovement.objects.filter(
        company=company, product=product, movement_type=MovementType.TRANSFER_OUT
    ).count() == 2


def test_concurrent_stock_adjustments_both_apply(tenant_a):
    """Two concurrent ADJUSTMENTs (+3 and -2) on one item -> no lost update.

    Final balance = opening + both deltas, and exactly two adjustment movements.
    """
    _require_postgres()
    company = tenant_a.company
    product = make_product(company, sku="RACE-ADJ")
    add_stock(tenant_a, product, "10")
    deltas = [Decimal("3"), Decimal("-2")]

    def work(i):
        return InventoryService.post_movement(
            company=company,
            product=product,
            movement_type=MovementType.ADJUSTMENT,
            quantity=deltas[i],
            reason="race",
            reference_type="manual_adjustment",
            user=tenant_a.owner,
        )

    results, errors = _run_concurrently(work)

    assert not errors, errors
    assert len(results) == 2
    assert StockBalance.objects.get(company=company, product=product).on_hand == Decimal("11")
    adjustments = StockMovement.objects.filter(
        company=company, product=product, movement_type=MovementType.ADJUSTMENT
    )
    assert adjustments.count() == 2
    assert sum(m.quantity for m in adjustments) == Decimal("1")


def test_concurrent_goods_receipt_completion_receives_stock_once(tenant_a):
    """Two completes of the same PO-linked GRN -> stock received once, second refused.

    GoodsReceiptService.complete locks the GRN row (select_for_update) and
    rejects any non-DRAFT status, so the loser gets BusinessRuleError.
    """
    _require_postgres()
    from purchases.grn_service import GoodsReceiptService
    from purchases.models import GoodsReceipt, GoodsReceiptItem, PurchaseOrder

    company = tenant_a.company
    supplier = make_supplier(company)
    product = make_product(company, sku="RACE-GRN")
    po = PurchaseOrder.objects.create(company=company, supplier=supplier)
    grn = GoodsReceipt.objects.create(
        company=company, supplier=supplier, purchase_order=po,
        warehouse=InventoryService.default_warehouse(company),
    )
    GoodsReceiptItem.objects.create(
        company=company, goods_receipt=grn, product=product,
        quantity_received=Decimal("7"), quantity_accepted=Decimal("7"),
        unit_price=Decimal("80"),
    )

    results, errors = _run_concurrently(lambda i: GoodsReceiptService.complete(grn, tenant_a.owner))

    assert len(results) == 1, (results, errors)
    assert len(errors) == 1 and isinstance(errors[0], BusinessRuleError), errors
    assert StockBalance.objects.get(company=company, product=product).on_hand == Decimal("7")
    assert StockMovement.objects.filter(
        company=company, product=product, reference_type="goods_receipt", reference_id=str(grn.pk)
    ).count() == 1
    grn.refresh_from_db()
    assert grn.status == GoodsReceipt.Status.COMPLETED


def test_concurrent_customer_edits_of_different_fields_do_not_lose_updates(tenant_a, monkeypatch):
    """Two PATCHes of one customer (credit_limit vs notes) both land.

    Real behaviour under test: CustomerViewSet has no version/revision field,
    no If-Match and no row lock; DRF's ModelSerializer.update does a full-row
    instance.save(). Both requests load the customer, then (forced here by a
    barrier just before perform_update, so the interleaving is deterministic)
    both save a stale full row -> last writer wins and the other edit is lost.
    """
    _require_postgres()
    from masters.views import CustomerViewSet

    customer = make_customer(tenant_a.company, credit_limit=Decimal("1000"), notes="orig")
    sync = threading.Barrier(2, timeout=10)
    original = CustomerViewSet.perform_update

    def synced_perform_update(self, serializer):
        sync.wait()  # both requests hold a stale copy of the row
        return original(self, serializer)

    monkeypatch.setattr(CustomerViewSet, "perform_update", synced_perform_update)

    payloads = [{"credit_limit": "5000.00"}, {"notes": "edited by B"}]

    def work(i):
        client = APIClient()
        client.force_authenticate(user=tenant_a.owner)
        resp = client.patch(f"/api/v1/customers/{customer.pk}/", payloads[i], format="json")
        assert resp.status_code == 200, resp.data
        return resp.status_code

    results, errors = _run_concurrently(work)

    assert not errors, errors
    customer.refresh_from_db()
    assert customer.credit_limit == Decimal("5000.00")
    assert customer.notes == "edited by B"


def test_concurrent_duplicate_gstr2b_upload_adds_no_duplicate_rows(tenant_a):
    """The same GSTR-2B file uploaded twice at once (and once more later) -> one row per document.

    Backed by uniq_gstr2b_ingest_doc plus update_or_create in
    Gstr2bIngestViewSet.upload.
    """
    _require_postgres()
    from accounts.models import User
    from reporting.models import Gstr2bIngest

    company = tenant_a.company
    company.feature_flags = {**(company.feature_flags or {}), "ENABLE_GSTR": True}
    company.save(update_fields=["feature_flags"])
    User.objects.filter(pk=tenant_a.owner.pk).update(active_company=company)

    payload = {
        "period": PERIOD,
        "rows": [
            {"supplier_gstin": "27AAAAA0000A1Z2", "invoice_number": "RACE-INV-1",
             "taxable_value": "100.00", "cgst": "9.00", "sgst": "9.00", "igst": "0.00"},
            {"supplier_gstin": "27AAAAA0000A1Z2", "invoice_number": "RACE-INV-2",
             "taxable_value": "200.00", "cgst": "0.00", "sgst": "0.00", "igst": "36.00"},
        ],
    }

    def work(i):
        client = APIClient()
        client.force_authenticate(user=tenant_a.owner)
        resp = client.post("/api/v1/reports/gstr2b/upload/", payload, format="json")
        return resp.status_code

    results, errors = _run_concurrently(work)

    assert not errors, errors
    assert results == [200, 200], results
    rows = Gstr2bIngest.objects.filter(company=tenant_a.company, period=PERIOD)
    assert rows.count() == 2
    assert sorted(rows.values_list("invoice_number", flat=True)) == ["RACE-INV-1", "RACE-INV-2"]

    # A later re-upload of the identical file is also a no-op for row count.
    client = APIClient()
    client.force_authenticate(user=tenant_a.owner)
    assert client.post("/api/v1/reports/gstr2b/upload/", payload, format="json").status_code == 200
    assert rows.count() == 2
