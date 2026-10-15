"""Pay-at-entry races that only PostgreSQL row locks can settle (Purchase review WP-1).

SQLite does not enforce row locks, so these skip unless the database is PostgreSQL.
"""

from __future__ import annotations

import threading
from decimal import Decimal

import pytest
from django.db import connection
from django.db.models import Sum

from payments.models import PaymentAllocation, SupplierPayment
from purchases.models import PurchaseInvoice
from purchases.pay_now import record_payment_at_entry
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


def test_two_parallel_payments_cannot_overpay_a_bill(tenant_a):
    product = make_product(tenant_a.company, sku="PNRACE-1", gst_rate="0")
    supplier = make_supplier(tenant_a.company, name="Race Supplies")
    draft = create_draft_purchase(
        tenant_a, supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{draft['id']}/complete/").status_code == 200
    invoice = PurchaseInvoice.objects.get(pk=draft["id"])

    def pay():
        return record_payment_at_entry(invoice, tenant_a.owner, {"amount": Decimal("70.00"), "mode": "CASH"})

    results = _run_together(pay, pay)
    wins = [r for r in results if isinstance(r, tuple)]
    losses = [r for r in results if isinstance(r, BaseException)]
    # 70 + 70 > 100: exactly one may land, and the loser must leave no payment row behind.
    assert len(wins) == 1 and len(losses) == 1, results
    allocated = PaymentAllocation.objects.filter(
        purchase_invoice=invoice, reversed_at__isnull=True
    ).aggregate(t=Sum("amount"))["t"]
    assert allocated == Decimal("70.00")
    assert SupplierPayment.objects.count() == 1
