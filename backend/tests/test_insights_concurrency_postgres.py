"""INP-01 / INP-15: the assistant confirm lock and the live-alert uniqueness hold under a real race.

SQLite does not enforce row locks, so these run only against PostgreSQL.
"""
from __future__ import annotations

import threading

import pytest
from django.db import connection
from rest_framework.test import APIClient

from core.models import Notification
from insights.models import AssistantMessage, AssistantThread, BusinessAlertEvent
from insights.services import upsert_alerts
from masters.models import Customer

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.postgres]


def _require_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row-level locking (select_for_update)")


def _race(user, calls):
    barrier = threading.Barrier(len(calls), timeout=15)
    results: list = [None] * len(calls)

    def runner(index, call):
        connection.close()
        client = APIClient()
        client.force_authenticate(user=user)
        try:
            barrier.wait()
            results[index] = call(client)
        except Exception as exc:  # pragma: no cover - surfaced by the assertions
            results[index] = exc
        finally:
            connection.close()

    threads = [threading.Thread(target=runner, args=(i, c)) for i, c in enumerate(calls)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results


def test_two_simultaneous_confirms_send_exactly_one_reminder(tenant_a):
    _require_postgres()
    cust = Customer.objects.create(company=tenant_a.company, name="Race Me", state="Karnataka", email="race@ex.com")
    thread = AssistantThread.objects.create(company=tenant_a.company, created_by=tenant_a.owner)
    msg = AssistantMessage.objects.create(
        thread=thread, role="assistant", content="draft",
        proposed_action={"type": "send_reminder", "text": "Please pay", "customer_id": cust.id},
    )

    def confirm(client):
        return client.post("/api/v1/insights/assistant/actions/confirm/", {"messageId": msg.id}, format="json")

    results = _race(tenant_a.owner, [confirm, confirm])
    codes = sorted(getattr(r, "status_code", 0) for r in results)
    assert codes == [200, 400], results
    assert Notification.objects.filter(company=tenant_a.company, recipient="race@ex.com").count() == 1


def test_concurrent_alert_refreshes_leave_one_live_row_per_rule(tenant_a):
    _require_postgres()
    BusinessAlertEvent.objects.create(
        company=tenant_a.company, code="SEED", severity="info", message="seed", subject_key="s",
    )

    def refresh(client):
        return client.post("/api/v1/insights/alerts/refresh/", {}, format="json")

    results = _race(tenant_a.owner, [refresh, refresh, refresh])
    assert all(getattr(r, "status_code", 0) == 200 for r in results), results
    live = list(
        BusinessAlertEvent.objects.filter(company=tenant_a.company, status__in=["OPEN", "SNOOZED"])
        .values_list("code", "subject_key")
    )
    assert len(live) == len(set(live))
    assert upsert_alerts(tenant_a.company) is not None
