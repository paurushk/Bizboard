"""A receipt and an invoice Complete for the same customer, at the same time, must both succeed.

Found 2026-10-22 while seeding with parallel workers (shadow books: every company posts journals).
The interleaving that deadlocked:

1. Receipt (A) posts its journal and holds the company's journal-number row until commit.
2. Complete (B) locked the customer FOR UPDATE for the credit-limit check, then waited for that row.
3. A's commit runs its deferred foreign-key check, which needs KEY SHARE on the customer: blocked by B.

Postgres aborted one of them. Complete now takes FOR NO KEY UPDATE, which still serialises two
Completes for one customer but does not block a foreign-key check. This test forces the order above.
"""

from __future__ import annotations

import threading
import time
from decimal import Decimal

import pytest
from django.db import connection, transaction

from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.postgres]


def _require_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row-level locking (select_for_update)")


def test_a_receipt_committing_while_a_complete_holds_the_customer_does_not_deadlock(tenant_a):
    _require_postgres()
    from payments.services import PaymentService
    from sales.models import SalesInvoice
    from sales.services import SalesService

    company = tenant_a.company
    product = make_product(company, sku="DL-1")
    add_stock(tenant_a, product, "5")
    customer = make_customer(company, state="Karnataka")
    draft = create_draft_invoice(tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100"}])
    invoice = SalesInvoice.objects.get(pk=draft["id"])

    receipt_posted = threading.Event()
    errors: list[BaseException] = []

    def receipt():
        connection.close()
        try:
            with transaction.atomic():
                PaymentService.create_receipt(
                    company=company, customer=customer, amount=Decimal("50.00"), mode="CASH", user=tenant_a.owner,
                )
                receipt_posted.set()
                time.sleep(1.5)  # let the Complete lock the customer and queue on the journal number
        except BaseException as exc:  # noqa: BLE001 - the thread reports every failure
            errors.append(exc)
            receipt_posted.set()
        finally:
            connection.close()

    def complete():
        connection.close()
        try:
            assert receipt_posted.wait(10)
            SalesService.complete(invoice, tenant_a.owner)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=receipt), threading.Thread(target=complete)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert errors == [], errors
    invoice.refresh_from_db()
    assert invoice.status == SalesInvoice.Status.COMPLETED
