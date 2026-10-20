"""Needs attention: two people acting on the same row at the same moment.

SQLite does not enforce row locks, so these skip unless the database is PostgreSQL.
"""

from __future__ import annotations

import threading

import pytest
from django.db import connection

from core.exceptions import BusinessRuleError
from core.models import AuditEvent
from insights.attention import dismiss_attention_row, reopen_attention_row, snooze_attention_row
from insights.models import AttentionOutcome, AttentionRowState

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.postgres]

KEY = "DEAD_STOCK:product:901"


def _require_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row-level locking (select_for_update)")


def _race(workers):
    results, errors = [], []
    barrier = threading.Barrier(len(workers), timeout=15)

    def run(work):
        connection.close()
        try:
            barrier.wait()
            results.append(work())
        except Exception as exc:  # collected so the test can say what went wrong
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=run, args=(work,)) for work in workers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results, errors


def _cu(tenant, user):
    return tenant.company.memberships.get(user=user)


def test_two_people_dismissing_the_same_row_leave_one_state_and_two_audit_records(tenant_a):
    _require_postgres()
    owner, staff = _cu(tenant_a, tenant_a.owner), _cu(tenant_a, tenant_a.staff)
    staff.can_view_financial_reports = True
    staff.save(update_fields=["can_view_financial_reports"])

    results, errors = _race([
        lambda: dismiss_attention_row(tenant_a.company, owner, dedupe_key=KEY, reason="owner says so"),
        lambda: dismiss_attention_row(tenant_a.company, staff, dedupe_key=KEY, reason="staff says so"),
    ])
    assert errors == [] and len(results) == 2
    assert AttentionRowState.objects.filter(company=tenant_a.company, dedupe_key=KEY).count() == 1
    assert AttentionRowState.objects.get(company=tenant_a.company, dedupe_key=KEY).dismissed is True
    assert AuditEvent.objects.filter(company=tenant_a.company, action="attention.dismissed").count() == 2
    # The learning report counts one dismissal per row, not one per click.
    assert AttentionOutcome.objects.filter(company=tenant_a.company, dedupe_key=KEY).count() == 1


def test_a_snooze_and_a_dismiss_at_once_end_in_one_consistent_state(tenant_a):
    _require_postgres()
    owner = _cu(tenant_a, tenant_a.owner)
    results, errors = _race([
        lambda: snooze_attention_row(tenant_a.company, owner, dedupe_key=KEY, days=3, reason="later"),
        lambda: dismiss_attention_row(tenant_a.company, owner, dedupe_key=KEY, reason="not needed"),
    ])
    assert errors == [] and len(results) == 2
    state = AttentionRowState.objects.get(company=tenant_a.company, dedupe_key=KEY)
    # Whichever ran last wins whole: never a row both dismissed and carrying the other's half.
    assert state.dismissed != bool(state.snooze_until), (state.dismissed, state.snooze_until)
    assert AuditEvent.objects.filter(company=tenant_a.company, entity_type="AttentionRow").count() == 2


def test_two_reopens_of_one_row_do_not_both_succeed(tenant_a):
    _require_postgres()
    owner = _cu(tenant_a, tenant_a.owner)
    dismiss_attention_row(tenant_a.company, owner, dedupe_key=KEY)
    results, errors = _race([
        lambda: reopen_attention_row(tenant_a.company, owner, dedupe_key=KEY),
        lambda: reopen_attention_row(tenant_a.company, owner, dedupe_key=KEY),
    ])
    assert len(results) == 1 and len(errors) == 1
    assert isinstance(errors[0], BusinessRuleError)
    assert AuditEvent.objects.filter(company=tenant_a.company, action="attention.reopened").count() == 1
