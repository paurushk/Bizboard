"""Credit / debit note races that only PostgreSQL row locks can settle (NEW-03).

SQLite does not enforce row locks, so these skip unless the database is
PostgreSQL, like tests/test_sales_returns_concurrency_postgres.py.
"""

from __future__ import annotations

import threading
from decimal import Decimal

import pytest
from django.db import connection
from django.db.models import Sum

from sales.models import SalesCreditNote, SalesDebitNote, SalesInvoice
from sales.notes_services import SalesNotesService
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

# Skip at collection, before any database fixture runs (see the sales returns twin).
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


def _invoice(tenant):
    product = make_product(tenant.company, sku="NRACE-1")
    add_stock(tenant, product, "20")
    customer = make_customer(tenant.company, name="Race Co")
    inv = create_draft_invoice(tenant, customer, [{"product": product.id, "quantity": "5", "unit_price": "100"}])
    assert tenant.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    return product, customer, inv


def _draft(tenant, kind, customer, inv, product, price):
    created = tenant.client.post(
        f"/api/v1/sales/{kind}-notes/",
        {
            "customer": customer.id,
            "sales_invoice": inv["id"],
            "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": "1", "unit_price": price}],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    return created.data["id"]


def test_two_credit_notes_completing_together_cannot_credit_more_than_the_invoice(tenant_a):
    product, customer, inv = _invoice(tenant_a)  # invoice total 590
    # Each note alone fits (400), both together do not (800 > 590).
    ids = [_draft(tenant_a, "credit", customer, inv, product, "339") for _ in range(2)]

    def complete(note_id):
        def job():
            return SalesNotesService.complete_credit_note(
                SalesCreditNote.objects.get(pk=note_id), tenant_a.owner,
                confirm_paid_invoice=True, confirm_price_override=True,
            )

        return job

    results = _run_together(*(complete(i) for i in ids))
    done = [r for r in results if not isinstance(r, BaseException)]
    failed = [r for r in results if isinstance(r, BaseException)]
    assert len(done) == 1 and len(failed) == 1, results
    total = SalesCreditNote.objects.filter(
        sales_invoice_id=inv["id"], status=SalesCreditNote.Status.COMPLETED
    ).aggregate(s=Sum("grand_total"))["s"]
    assert total <= Decimal(str(SalesInvoice.objects.get(pk=inv["id"]).grand_total))


def test_two_debit_notes_completing_together_respect_the_invoice_value_cap(tenant_a):
    product, customer, inv = _invoice(tenant_a)
    # Each debit alone is under the 590 invoice value; together they would pass it.
    ids = [_draft(tenant_a, "debit", customer, inv, product, "400") for _ in range(2)]

    def complete(note_id):
        def job():
            return SalesNotesService.complete_debit_note(
                SalesDebitNote.objects.get(pk=note_id), tenant_a.owner, confirm_additional_debit=True,
            )

        return job

    results = _run_together(*(complete(i) for i in ids))
    done = [r for r in results if not isinstance(r, BaseException)]
    failed = [r for r in results if isinstance(r, BaseException)]
    assert len(done) == 1 and len(failed) == 1, results
    total = SalesDebitNote.objects.filter(
        sales_invoice_id=inv["id"], status=SalesDebitNote.Status.COMPLETED
    ).aggregate(s=Sum("grand_total"))["s"]
    assert total <= Decimal(str(SalesInvoice.objects.get(pk=inv["id"]).grand_total))
