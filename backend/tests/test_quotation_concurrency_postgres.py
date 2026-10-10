"""Quotation races that only PostgreSQL row locks can settle (closure plan E1).

SQLite does not enforce row locks, so these skip unless the database is
PostgreSQL (CI with DATABASE_URL), like tests/test_concurrency_races.py.
"""

from __future__ import annotations

import threading
from decimal import Decimal

import pytest
from django.db import connection
from django.db.models import Sum

from core.exceptions import BusinessRuleError
from sales.models import Quotation, QuotationConversion
from sales.quotation_conversions import QuotationConversionService
from sales.services import SalesService
from tests.conftest import make_customer, make_product

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.postgres]


def _require_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row-level locking (select_for_update)")


def _quote(tenant, qty="10"):
    product = make_product(tenant.company, sku="QRACE-1")
    customer = make_customer(tenant.company, name="Race Co")
    resp = tenant.client.post(
        "/api/v1/sales/quotations/",
        {
            "customer": customer.id,
            "valid_until": "2099-01-01",
            "items": [{"product": product.id, "quantity": qty, "unit_price": "100.00", "gst_rate": "18"}],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    return Quotation.objects.get(pk=resp.data["id"]), product


def _run_together(*jobs):
    """Run each job in its own thread and connection, released at the same moment."""
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


def _assert_ledger_matches(quote_id):
    quote = Quotation.objects.get(pk=quote_id)
    for item in quote.items.all():
        live = (
            QuotationConversion.objects.filter(quotation_item=item, released_at__isnull=True)
            .aggregate(total=Sum("quantity"))["total"]
            or Decimal("0")
        )
        assert item.converted_quantity == live
        assert item.converted_quantity <= item.quantity
    assert not QuotationConversion.objects.filter(
        quotation_id=quote_id, quotation_item__isnull=True, released_at__isnull=True
    ).exists()


def test_two_partial_conversions_never_convert_more_than_the_quote_holds(tenant_a):
    _require_postgres()
    quote, _ = _quote(tenant_a, "10")
    item_id = quote.items.get().id

    def convert():
        fresh = Quotation.objects.get(pk=quote.pk)
        return SalesService.convert_quotation_to_order(
            fresh, tenant_a.owner, line_quantities=[{"id": item_id, "quantity": 6}]
        )

    results = _run_together(convert, convert)
    wins = [r for r in results if not isinstance(r, BaseException)]
    losses = [r for r in results if isinstance(r, BusinessRuleError)]
    assert len(wins) == 1 and len(losses) == 1, results
    assert Quotation.objects.get(pk=quote.pk).items.get().converted_quantity == Decimal("6")
    assert QuotationConversion.objects.filter(quotation=quote).count() == 1
    _assert_ledger_matches(quote.pk)


def test_edit_and_conversion_at_the_same_moment_keep_the_ledger_whole(tenant_a):
    _require_postgres()
    quote, product = _quote(tenant_a, "10")
    item_id = quote.items.get().id

    def convert():
        fresh = Quotation.objects.get(pk=quote.pk)
        return SalesService.convert_quotation_to_order(
            fresh, tenant_a.owner, line_quantities=[{"id": item_id, "quantity": 4}]
        )

    def edit():
        fresh = Quotation.objects.get(pk=quote.pk)
        return SalesService.set_quotation_items(
            fresh,
            [{"product": product, "quantity": Decimal("8"), "unit_price": Decimal("100"), "gst_rate": Decimal("18")}],
            tenant_a.owner,
        )

    results = _run_together(convert, edit)
    unexpected = [r for r in results if isinstance(r, BaseException) and not isinstance(r, BusinessRuleError)]
    assert not unexpected, results
    _assert_ledger_matches(quote.pk)


def test_sweep_running_while_a_conversion_commits_does_not_corrupt_the_ledger(tenant_a):
    _require_postgres()
    quote, _ = _quote(tenant_a, "10")
    item_id = quote.items.get().id

    def convert():
        fresh = Quotation.objects.get(pk=quote.pk)
        return SalesService.convert_quotation_to_order(
            fresh, tenant_a.owner, line_quantities=[{"id": item_id, "quantity": 5}]
        )

    def sweep():
        return QuotationConversionService.sweep(tenant_a.company)

    results = _run_together(convert, sweep)
    unexpected = [r for r in results if isinstance(r, BaseException) and not isinstance(r, BusinessRuleError)]
    assert not unexpected, results
    _assert_ledger_matches(quote.pk)
    # A live order exists, so its row must not have been swept.
    assert QuotationConversion.objects.filter(quotation=quote, released_at__isnull=True).count() == 1
