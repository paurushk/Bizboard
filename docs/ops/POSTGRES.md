# Postgres + PgBouncer (7.1 / 7.3)

## Timeouts already in Django

`backend/config/settings.py` sets libpq options when the engine is Postgres:

- `statement_timeout=30000` (30s)
- `idle_in_transaction_session_timeout=60000` (60s)

Do not raise these to “unlimited” to hide slow queries. Fix the query.

SQLite local tests ignore both. CI Postgres jobs exercise them.

## Recommended server knobs (Human applies)

Pilot-sized. Tune after `pg_stat_statements`, not from this file:

- `shared_buffers` ≈ 25% RAM on a dedicated DB box
- `work_mem` small (4–16MB) — many tenants, many sorts
- `max_connections` sized for api+worker+beat+one admin, **or** PgBouncer
  `default_pool_size` if pooling is on
- WAL / backups: follow `docs/pilot/RUNBOOKS.md` dump cadence

## PgBouncer (WP-5, BB-068)

Built and tested on local staging 2026-10-25; **off by default**. The overlay
[`docker-compose.pgbouncer.yml`](../../docker-compose.pgbouncer.yml) puts PgBouncer 1.25.2
([`deploy/pgbouncer.ini`](../../deploy/pgbouncer.ini)) between api/worker/beat and Postgres.
`migrate`, backups and restores keep connecting to `db` directly as the owner.

**Recommendation: start production without it** (direct connections, `DB_CONN_MAX_AGE=600`).
Turn it on only when the number of Postgres connections becomes the limit (more api/worker
replicas than `max_connections` allows). On the laptop it was slower, because every request then
opens and signs in a new client connection (table below). Re-measure on the host before deciding.

**Pool mode is `session` (SR0-06).** `core/rls.py` binds the tenant with a session-level
`set_config(..., false)` in autocommit. In `transaction` mode the next statement can land on a
backend that still carries another tenant's `app.company_id`. Do not switch to transaction mode
until WP-C4 (tenant bound with `SET LOCAL` inside each transaction) ships with its test.
`server_reset_query = DISCARD ALL` clears `app.company_id` when a client leaves (tested).

**What the overlay sets, and why**

| Setting | Why |
|---|---|
| `DB_CONN_MAX_AGE=0`, `DB_VIA_PGBOUNCER=1` on api/worker/beat | PgBouncer does the pooling; a long-lived Django connection would pin a server connection. Settings **refuse to boot** with `DB_VIA_PGBOUNCER=1` and a non-zero `CONN_MAX_AGE` |
| Timeouts on the app role (`ALTER ROLE ... SET statement_timeout = '30s'`, `idle_in_transaction_session_timeout = '60s'`, in `scripts/sql/app_role.sql`) | PgBouncer accepts the libpq startup `options` that `settings.py` sends and drops it (`ignore_startup_parameters`). Without the role settings both timeouts would be silently off through the pool. Keep the two in step with BB-000546 in `settings.py` |
| `auth_query` through `pgbouncer_auth` → `pgbouncer.user_lookup()` | No app password or SCRAM verifier on disk. The lookup role can only call that `SECURITY DEFINER` function; it returns non-superuser roles only, so the owner cannot sign in through the pool. Its own password (`PGBOUNCER_AUTH_PASSWORD`) is written to a tmpfs file at container start |
| No published port | Only the app containers on the compose network reach it |

**Turning it on**

1. Set `PGBOUNCER_AUTH_PASSWORD` (a long random value) in the env file.
2. Run the app-role script (`scripts/staging-db-role.sh` or `scripts/db-app-role.sh <env> <compose files>`):
   it creates `pgbouncer_auth`, the lookup function and the role timeouts.
3. `docker compose ... -f docker-compose.pgbouncer.yml up -d pgbouncer`, then `up -d --no-deps api worker beat`.
4. Check: `SHOW statement_timeout` from the api container is `30s`; `/api/v1/health/?ready=1` is 200.
5. Turn it off: restart api/worker/beat without the overlay, then stop `pgbouncer`.

**Tests** (`backend/tests/test_pgbouncer_pool.py`): the boot guard always runs. The pool checks run
when `PGBOUNCER_TEST_DSN` (and `PGBOUNCER_OWNER_DSN`) point at the pool. They check that the role
timeouts come through, that a wrong password and the superuser are refused, that the app role
cannot call the lookup and the lookup role cannot read tables, and that `app.company_id` never
carries over to the next client. CI renders the overlay for staging and prod (`docker` job). The
pytest RLS lane cannot run through the pool, because creating the test database needs the owner,
which the pool refuses. So the tenant-setting carry-over test above stands in for it.

**Local results, 2026-10-25** (`load/pool_compare.py`: read mix of invoice list, dashboard and
search; 10 threads, one sales login, 90 s; laptop, so only the comparison means anything)

| Run | Requests | Errors | Req/s | p50 | p95 |
|---|---|---|---|---|---|
| Through the pool | 131 | 0 | 1.5 | 6.8 s | 11.9 s |
| Through the pool, repeat after warm-up | 177 | 0 | 2.0 | 4.8 s | 10.0 s |
| Direct (`CONN_MAX_AGE=600`) | 201 | 0 | 2.2 | 4.5 s | 7.9 s |

The worker was at full CPU after each restart, which adds noise. The pool did not fail any request
and did not leak a tenant; it is simply not faster at this scale.
