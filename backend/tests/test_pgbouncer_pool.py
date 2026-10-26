"""WP-5 (BB-068): PgBouncer in front of api/worker/beat.

The settings guard always runs. The pool checks run only when PGBOUNCER_TEST_DSN points at a
PgBouncer (docker-compose.pgbouncer.yml), e.g. from inside the staging api container:

    PGBOUNCER_TEST_DSN=postgresql://<app user>:<pw>@pgbouncer:6432/<db> \
    PGBOUNCER_OWNER_DSN=postgresql://<owner>:<pw>@pgbouncer:6432/<db> \
    python -m pytest tests/test_pgbouncer_pool.py -p no:cacheprovider
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest

BACKEND = Path(__file__).resolve().parents[1]
POOL_DSN = os.environ.get("PGBOUNCER_TEST_DSN", "")
OWNER_DSN = os.environ.get("PGBOUNCER_OWNER_DSN", "")


def _import_settings(**env):
    full = {
        **{k: v for k, v in os.environ.items() if not k.startswith(("DB_", "DATABASE_"))},
        "DJANGO_ENV": "development",
        "DATABASE_URL": "postgresql://u:p@127.0.0.1:5432/x",
        **env,
    }
    full.pop("DJANGO_SETTINGS_MODULE", None)
    return subprocess.run(
        [sys.executable, "-c", "import config.settings"],
        cwd=BACKEND, env=full, capture_output=True, text=True, timeout=120,
    )


def test_settings_refuse_persistent_connections_behind_pgbouncer():
    bad = _import_settings(DB_VIA_PGBOUNCER="1", DB_CONN_MAX_AGE="600")
    assert bad.returncode != 0
    assert "DB_VIA_PGBOUNCER=1 needs DB_CONN_MAX_AGE=0" in bad.stderr
    ok = _import_settings(DB_VIA_PGBOUNCER="1", DB_CONN_MAX_AGE="0")
    assert ok.returncode == 0, ok.stderr[-2000:]


pool = pytest.mark.skipif(not POOL_DSN, reason="PGBOUNCER_TEST_DSN not set (needs the pgbouncer overlay)")


def _connect(dsn):
    import psycopg

    return psycopg.connect(dsn, autocommit=True, connect_timeout=10)


def _with_password(dsn, password):
    parts = urlsplit(dsn)
    netloc = f"{parts.username}:{password}@{parts.hostname}:{parts.port}"
    return urlunsplit(parts._replace(netloc=netloc))


@pool
def test_role_timeouts_hold_through_the_pool():
    with _connect(POOL_DSN) as conn:
        assert conn.execute("SHOW statement_timeout").fetchone()[0] == "30s"
        assert conn.execute("SHOW idle_in_transaction_session_timeout").fetchone()[0] == "1min"
        assert conn.execute("SELECT inet_server_port()").fetchone()[0] == 5432
        assert conn.execute("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user").fetchone()[0] is False


@pool
def test_a_wrong_password_is_refused():
    import psycopg

    with pytest.raises(psycopg.OperationalError):
        _connect(_with_password(POOL_DSN, "definitely-not-the-password"))


@pool
@pytest.mark.skipif(not OWNER_DSN, reason="PGBOUNCER_OWNER_DSN not set")
def test_a_superuser_cannot_sign_in_through_the_pool():
    import psycopg

    with pytest.raises(psycopg.OperationalError):
        _connect(OWNER_DSN)


@pool
def test_the_lookup_role_can_read_nothing_but_the_lookup():
    """pgbouncer_auth may call pgbouncer.user_lookup() and nothing else; the app role may not call it."""
    import psycopg

    with _connect(POOL_DSN) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT * FROM pgbouncer.user_lookup(current_user)")
    with _connect(POOL_DSN) as conn:
        assert conn.execute(
            "SELECT has_table_privilege('pgbouncer_auth', 'accounts_company', 'select')"
        ).fetchone()[0] is False


@pool
def test_the_tenant_setting_never_carries_over_to_the_next_client():
    """Session mode + DISCARD ALL: a released server connection forgets app.company_id."""
    for company_id in ("101", "202", "303", "404"):
        with _connect(POOL_DSN) as conn:
            leftover = conn.execute("SELECT current_setting('app.company_id', true)").fetchone()[0]
            assert leftover in (None, ""), f"previous client's company leaked: {leftover!r}"
            conn.execute("SELECT set_config('app.company_id', %s, false)", [company_id])
            assert conn.execute("SELECT current_setting('app.company_id', true)").fetchone()[0] == company_id
