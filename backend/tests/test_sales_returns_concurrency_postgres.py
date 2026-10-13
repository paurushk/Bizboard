"""Sales return races that only PostgreSQL row locks can settle (SRF-07).

SQLite does not enforce row locks, so these skip unless the database is
PostgreSQL, like tests/test_quotation_concurrency_postgres.py.
"""

from __future__ import annotations

import threading
from decimal import Decimal

import pytest
from django.db import connection
from django.db.models import Sum

from sales.models import SalesItem, SalesReturn, SalesReturnItem
from sales.services import SalesService
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

# Skip at collection, before any database fixture runs: a transaction=True test that
# skips inside its body still flushes the database on teardown, which empties the
# seeded reference rows (e.g. HSN rates) for every test that runs after it on SQLite.
pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.postgres,
    pytest.mark.skipif(
        connection.vendor != "postgresql",
        reason="Requires PostgreSQL row-level locking (select_for_update)",
    ),
]


def _require_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row-level locking (select_for_update)")


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


def _invoice_with_two_draft_returns(tenant, sold="5", each="4"):
    product = make_product(tenant.company, sku="RRACE-1")
    add_stock(tenant, product, "20")
    customer = make_customer(tenant.company, name="Race Co")
    inv = create_draft_invoice(tenant, customer, [{"product": product.id, "quantity": sold, "unit_price": "100"}])
    assert tenant.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    src = SalesItem.objects.get(invoice_id=inv["id"])
    ids = []
    for _ in range(2):
        created = tenant.client.post(
            "/api/v1/sales/returns/",
            {
                "customer": customer.id,
                "sales_invoice": inv["id"],
                "items": [{"product": product.id, "quantity": each, "unit_price": "100", "source_item": src.id}],
            },
            format="json",
        )
        assert created.status_code == 201, created.data
        ids.append(created.data["id"])
    return product, src, ids


def test_two_returns_completing_together_cannot_return_more_than_was_sold(tenant_a):
    _require_postgres()
    _product, src, ids = _invoice_with_two_draft_returns(tenant_a)

    def complete(return_id):
        def job():
            return SalesService.complete_return(SalesReturn.objects.get(pk=return_id), tenant_a.owner)

        return job

    results = _run_together(*[complete(i) for i in ids])
    wins = [r for r in results if isinstance(r, SalesReturn)]
    assert len(wins) == 1, results
    returned = (
        SalesReturnItem.objects.filter(
            source_item=src, sales_return__status=SalesReturn.Status.COMPLETED
        ).aggregate(t=Sum("quantity"))["t"]
        or Decimal("0")
    )
    assert returned == Decimal("4")
    assert returned <= src.quantity


def test_complete_and_cancel_of_different_returns_leave_a_consistent_invoice(tenant_a):
    _require_postgres()
    _product, src, ids = _invoice_with_two_draft_returns(tenant_a, sold="6", each="3")
    first = SalesService.complete_return(SalesReturn.objects.get(pk=ids[0]), tenant_a.owner)

    def complete_second():
        return SalesService.complete_return(SalesReturn.objects.get(pk=ids[1]), tenant_a.owner)

    def cancel_first():
        return SalesService.cancel_return(SalesReturn.objects.get(pk=first.pk), tenant_a.owner)

    _run_together(complete_second, cancel_first)
    from sales.models import SalesInvoice

    invoice = SalesInvoice.objects.get(pk=src.invoice_id)
    returned = (
        SalesReturnItem.objects.filter(
            source_item=src, sales_return__status=SalesReturn.Status.COMPLETED
        ).aggregate(t=Sum("quantity"))["t"]
        or Decimal("0")
    )
    assert returned <= src.quantity
    fully = returned >= src.quantity
    assert (invoice.status == SalesInvoice.Status.RETURNED) == fully


def test_preview_totals_leaves_nothing_behind_when_not_wrapped_in_a_transaction(tenant_a):
    """The page's live summary calls preview on every edit; each call must be free.

    Runs with real commits (transaction=True), which is how a request behaves in
    production. A savepoint-only rollback passes inside pytest's wrapping
    transaction but leaves a draft return and credit note per call in real life.
    """
    from sales.models import SalesCreditNote

    product, src, _ids = _invoice_with_two_draft_returns(tenant_a, sold="5", each="1")
    returns_before = SalesReturn.objects.count()
    notes_before = SalesCreditNote.objects.count()
    for _ in range(3):
        resp = tenant_a.client.post(
            "/api/v1/sales/returns/preview-totals/",
            {
                "customer": src.invoice.customer_id,
                "sales_invoice": src.invoice_id,
                "items": [{"product": product.id, "quantity": "2", "unit_price": "100", "source_item": src.id}],
            },
            format="json",
        )
        assert resp.status_code == 200, resp.data
    assert SalesReturn.objects.count() == returns_before
    assert SalesCreditNote.objects.count() == notes_before
