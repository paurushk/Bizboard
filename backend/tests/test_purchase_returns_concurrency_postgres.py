"""Purchase return races that only PostgreSQL row locks can settle.

SQLite does not enforce row locks, so these skip (at collection, before any database
fixture runs) unless the database is PostgreSQL.
"""

from __future__ import annotations

import threading
from decimal import Decimal

import pytest
from django.db import connection
from django.db.models import Sum

from purchases.models import PurchaseInvoice, PurchaseItem, PurchaseReturn, PurchaseReturnItem
from purchases.services import PurchaseService
from tests.conftest import create_draft_purchase, make_product, make_supplier

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.postgres,
    pytest.mark.skipif(
        connection.vendor != "postgresql",
        reason="Requires PostgreSQL row-level locking (select_for_update)",
    ),
]


def _run_together(*jobs):
    barrier = threading.Barrier(len(jobs), timeout=15)
    results: list[object] = [None] * len(jobs)

    def wrap(index, job):
        connection.close()
        try:
            barrier.wait()
            results[index] = job()
        except BaseException as exc:  # noqa: BLE001 - the test inspects what each side raised
            results[index] = exc
        finally:
            connection.close()

    threads = [threading.Thread(target=wrap, args=(i, job)) for i, job in enumerate(jobs)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results


def _bill_with_two_draft_returns(tenant, bought="5", each="4"):
    product = make_product(tenant.company, sku="PRACE-1", gst_rate="0")
    supplier = make_supplier(tenant.company, name="Race Supplies")
    draft = create_draft_purchase(
        tenant, supplier,
        [{"product": product.id, "quantity": bought, "unit_price": "100", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    assert tenant.client.post(f"/api/v1/purchases/invoices/{draft['id']}/complete/").status_code == 200
    src = PurchaseItem.objects.get(invoice_id=draft["id"])
    ids = []
    for _ in range(2):
        created = tenant.client.post(
            "/api/v1/purchases/returns/",
            {
                "supplier": supplier.id,
                "purchase_invoice": draft["id"],
                "items": [{"product": product.id, "quantity": each, "unit_price": "100", "gst_rate": "0"}],
            },
            format="json",
        )
        assert created.status_code == 201, created.data
        ids.append(created.data["id"])
    return product, src, ids


def _returned(src):
    return (
        PurchaseReturnItem.objects.filter(
            purchase_return__purchase_invoice_id=src.invoice_id,
            purchase_return__status=PurchaseReturn.Status.COMPLETED,
        ).aggregate(t=Sum("quantity"))["t"]
        or Decimal("0")
    )


def test_two_returns_completing_together_cannot_return_more_than_was_bought(tenant_a):
    _product, src, ids = _bill_with_two_draft_returns(tenant_a)

    def complete(return_id):
        return lambda: PurchaseService.complete_return(PurchaseReturn.objects.get(pk=return_id), tenant_a.owner)

    results = _run_together(*[complete(i) for i in ids])
    assert len([r for r in results if isinstance(r, PurchaseReturn)]) == 1, results
    assert _returned(src) == Decimal("4")
    assert _returned(src) <= src.quantity


def test_complete_racing_cancel_leaves_a_consistent_bill(tenant_a):
    _product, src, ids = _bill_with_two_draft_returns(tenant_a, bought="6", each="3")
    first = PurchaseService.complete_return(PurchaseReturn.objects.get(pk=ids[0]), tenant_a.owner)

    def complete_second():
        return PurchaseService.complete_return(PurchaseReturn.objects.get(pk=ids[1]), tenant_a.owner)

    def cancel_first():
        return PurchaseService.cancel_return(PurchaseReturn.objects.get(pk=first.pk), tenant_a.owner)

    _run_together(complete_second, cancel_first)
    bill = PurchaseInvoice.objects.get(pk=src.invoice_id)
    assert _returned(src) <= src.quantity
    assert (bill.status == PurchaseInvoice.Status.RETURNED) == (_returned(src) >= src.quantity)


def test_preview_totals_leaves_nothing_behind_when_not_wrapped_in_a_transaction(tenant_a):
    """Runs with real commits, which is how a request behaves in production."""
    from purchases.models import PurchaseCreditNote

    product, src, _ids = _bill_with_two_draft_returns(tenant_a, bought="5", each="1")
    returns_before = PurchaseReturn.objects.count()
    notes_before = PurchaseCreditNote.objects.count()
    for _ in range(3):
        resp = tenant_a.client.post(
            "/api/v1/purchases/returns/preview-totals/",
            {
                "supplier": src.invoice.supplier_id,
                "purchase_invoice": src.invoice_id,
                "items": [{"product": product.id, "quantity": "2", "unit_price": "100", "gst_rate": "0"}],
            },
            format="json",
        )
        assert resp.status_code == 200, resp.data
    assert PurchaseReturn.objects.count() == returns_before
    assert PurchaseCreditNote.objects.count() == notes_before
