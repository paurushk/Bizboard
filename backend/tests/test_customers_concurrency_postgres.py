"""Customer write races that only PostgreSQL row locks can settle (CUS-09).

Skips unless the database is PostgreSQL, like tests/test_quotation_concurrency_postgres.py.
"""

from __future__ import annotations

import threading

import pytest
from django.db import connection
from rest_framework.test import APIClient

from tests.conftest import make_customer

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
        t.join(timeout=30)
    return results


def _client(tenant):
    client = APIClient()
    client.force_authenticate(user=tenant.owner)
    return client


def test_two_patches_with_the_same_version_only_one_wins(tenant_a):
    _require_postgres()
    c = make_customer(tenant_a.company)
    url = f"/api/v1/customers/{c.id}/"

    def patch(field, value):
        return lambda: _client(tenant_a).patch(url, {field: value, "version": c.version}, format="json").status_code

    codes = _together(patch("notes", "first"), patch("phone", "9876543210"))
    assert sorted(codes) == [200, 409]


def test_patches_without_version_both_land(tenant_a):
    _require_postgres()
    c = make_customer(tenant_a.company)
    url = f"/api/v1/customers/{c.id}/"

    def patch(field, value):
        return lambda: _client(tenant_a).patch(url, {field: value}, format="json").status_code

    codes = _together(patch("notes", "kept"), patch("phone", "9876543210"))
    assert codes == [200, 200]
    c.refresh_from_db()
    assert c.notes == "kept" and c.phone == "9876543210" and c.version == 3


def test_export_and_list_only_return_the_callers_company_under_rls(tenant_a, tenant_b):
    _require_postgres()
    make_customer(tenant_a.company, name="Alpha Only")
    make_customer(tenant_b.company, name="Beta Only")
    resp = _client(tenant_a).get("/api/v1/customers/export/")
    assert resp.status_code == 200
    body = b"".join(resp.streaming_content).decode()
    assert "Alpha Only" in body and "Beta Only" not in body
    names = [r["name"] for r in _client(tenant_a).get("/api/v1/customers/").data["results"]]
    assert "Alpha Only" in names and "Beta Only" not in names
