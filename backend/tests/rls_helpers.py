"""Run part of a test as the real app DB role (NOSUPERUSER NOBYPASSRLS).

The Postgres test database is owned by a superuser, and a superuser bypasses FORCE ROW LEVEL
SECURITY, so ordinary tests cannot see RLS bugs. Build the test data as the superuser, then do
the thing under test inside ``app_role()``: the session switches to a restricted role and RLS
applies exactly as it does for production's ``APP_DB_USER`` (scripts/sql/app_role.sql).
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from django.db import connection

ROLE = "bb_rls_test_app"

needs_pg = pytest.mark.skipif(connection.vendor != "postgresql", reason="Postgres row-level security")


def ensure_role() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [ROLE])
        if cursor.fetchone() is None:
            cursor.execute(f"CREATE ROLE {ROLE} NOSUPERUSER NOBYPASSRLS NOLOGIN")
        cursor.execute(f"GRANT USAGE ON SCHEMA public TO {ROLE}")
        cursor.execute(f"GRANT ALL ON ALL TABLES IN SCHEMA public TO {ROLE}")
        cursor.execute(f"GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO {ROLE}")


@contextmanager
def app_role():
    """Switch this connection to the restricted role for the duration of the block."""
    ensure_role()
    with connection.cursor() as cursor:
        cursor.execute(f"SET ROLE {ROLE}")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")


@pytest.fixture
def restricted_db_role(db):
    """The whole test body runs as the restricted role."""
    with app_role():
        yield
