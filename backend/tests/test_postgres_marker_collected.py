"""Canary: the postgres marker still runs when the database is Postgres.

On SQLite this skips, the same way the other postgres-marked tests do.
A CI job that uses Postgres and then skips the marker globally will not
execute the assertion below.
"""

import pytest
from django.db import connection

pytestmark = [pytest.mark.django_db, pytest.mark.postgres]


def test_postgres_marker_uses_postgresql():
    if connection.vendor != "postgresql":
        pytest.skip("SQLite is the local default; postgres-marked tests run via scripts/test_postgres.ps1")
    assert connection.vendor == "postgresql"
