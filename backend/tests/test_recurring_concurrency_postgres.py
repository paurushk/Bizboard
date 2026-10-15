"""Recurring "Run now" against the hourly beat: only PostgreSQL row locks can settle it.

Skips unless the database is PostgreSQL, like tests/test_customers_concurrency_postgres.py.
"""

from __future__ import annotations

import threading
from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from sales.models import RecurringInvoiceRun, RecurringInvoiceSchedule, SalesInvoice
from sales.recurring import generate_for_schedule, process_due_schedules
from tests.conftest import make_customer, make_product

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.postgres]


def _require_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row-level locking (select_for_update)")


def _together(*jobs):
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

    threads = [threading.Thread(target=wrap, args=(i, j)) for i, j in enumerate(jobs)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return results


def _due_schedule(tenant):
    customer = make_customer(tenant.company)
    product = make_product(tenant.company)
    return RecurringInvoiceSchedule.objects.create(
        company=tenant.company, customer=customer,
        cadence=RecurringInvoiceSchedule.Cadence.MONTHLY,
        next_run_at=timezone.now() - timedelta(minutes=5), anchor_day=timezone.now().day,
        line_template={"items": [{"product": product.id, "quantity": "1", "unit_price": "100"}]},
        created_by=tenant.owner, updated_by=tenant.owner,
    )


def test_two_manual_runs_for_the_same_period_make_one_document(tenant_a):
    _require_postgres()
    sched = _due_schedule(tenant_a)
    today = timezone.localdate()

    def run():
        return generate_for_schedule(sched, run_date=today, user=tenant_a.owner, manual=True)

    results = _together(run, run)
    assert not [r for r in results if isinstance(r, BaseException)], results
    assert sorted(r.created for r in results) == [False, True]
    assert RecurringInvoiceRun.objects.filter(schedule=sched).count() == 1
    assert SalesInvoice.objects.filter(company=tenant_a.company).count() == 1
    sched.refresh_from_db()
    assert sched.total_runs_count == 1


def test_run_now_racing_the_beat_makes_one_document(tenant_a):
    _require_postgres()
    sched = _due_schedule(tenant_a)

    def manual():
        return generate_for_schedule(
            sched, run_date=timezone.localdate(), user=tenant_a.owner, manual=True,
        ).created

    def beat():
        return process_due_schedules(now=timezone.now())["created"]

    results = _together(manual, beat)
    assert not [r for r in results if isinstance(r, BaseException)], results
    assert RecurringInvoiceRun.objects.filter(schedule=sched).count() == 1
    assert SalesInvoice.objects.filter(company=tenant_a.company).count() == 1
