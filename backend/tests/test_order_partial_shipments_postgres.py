"""Order races that only PostgreSQL row locks can settle (hardening plan R3, TC-WP6-12/13).

SQLite does not enforce row locks, so these skip unless the database is PostgreSQL (CI with
DATABASE_URL), like tests/test_quotation_concurrency_postgres.py.
"""

from __future__ import annotations

import threading
from decimal import Decimal

import pytest
from django.db import connection

from core.exceptions import BusinessRuleError
from inventory.models import MovementType, StockBalance, StockMovement
from sales.models import SalesOrder
from sales.notes_services import SalesNotesService
from sales.order_quantities import order_remaining
from sales.services import SalesService
from tests.conftest import add_stock, make_customer, make_product

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


def _confirmed_order(tenant, qty="10"):
    product = make_product(tenant.company, sku="RACE-SO")
    add_stock(tenant, product, "100")
    customer = make_customer(tenant.company, name="Race Co")
    resp = tenant.client.post(
        "/api/v1/sales/orders/",
        {
            "customer": customer.id, "invoice_type": "NON_GST",
            "items": [{"product": product.id, "quantity": qty, "unit_price": "100", "gst_rate": "0"}],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    order = SalesOrder.objects.get(pk=resp.data["id"])
    SalesNotesService.confirm_sales_order(order, tenant.owner)
    return order, product


def test_tc_wp6_12_two_converts_asking_for_the_last_units_one_wins(tenant_a):
    order, product = _confirmed_order(tenant_a)
    line_id = order.items.get().pk
    SalesNotesService.convert_sales_order_to_challan(
        order, tenant_a.owner, line_quantities={line_id: Decimal("4")}
    )

    def take_six():
        fresh = SalesOrder.objects.get(pk=order.pk)
        return SalesNotesService.convert_sales_order(
            fresh, tenant_a.owner, line_quantities={line_id: Decimal("6")}
        )

    def ship_six():
        fresh = SalesOrder.objects.get(pk=order.pk)
        return SalesNotesService.convert_sales_order_to_challan(
            fresh, tenant_a.owner, line_quantities={line_id: Decimal("6")}
        )

    results = _run_together(take_six, ship_six)
    wins = [r for r in results if not isinstance(r, BaseException)]
    losses = [r for r in results if isinstance(r, BusinessRuleError)]
    assert len(wins) == 1 and len(losses) == 1, results
    assert order_remaining(SalesOrder.objects.get(pk=order.pk)) == {product.id: Decimal("0")}


def test_tc_wp6_13_challan_and_direct_invoice_completing_together_post_stock_once(tenant_a):
    order, product = _confirmed_order(tenant_a, "10")
    line_id = order.items.get().pk
    challan = SalesNotesService.convert_sales_order_to_challan(
        order, tenant_a.owner, line_quantities={line_id: Decimal("5")}
    )
    invoice = SalesNotesService.convert_sales_order(
        SalesOrder.objects.get(pk=order.pk), tenant_a.owner, line_quantities={line_id: Decimal("5")}
    )

    def complete_challan():
        return SalesNotesService.complete_challan(challan, tenant_a.owner)

    def complete_invoice():
        return SalesService.complete(invoice, tenant_a.owner)

    results = _run_together(complete_challan, complete_invoice)
    unexpected = [r for r in results if isinstance(r, BaseException) and not isinstance(r, BusinessRuleError)]
    assert not unexpected, results
    assert StockBalance.objects.get(company=tenant_a.company, product=product).reserved == Decimal("0")
    sold = sum(
        abs(m.quantity)
        for m in StockMovement.objects.filter(
            company=tenant_a.company, product=product, movement_type=MovementType.SALE
        )
    )
    # The invoice posts its 5; the challan posts nothing unless the company stocks on challan.
    assert sold <= Decimal("10")
