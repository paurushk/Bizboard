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

## PgBouncer

Template: [`deploy/pgbouncer.ini`](../../deploy/pgbouncer.ini). **Not** wired into
`docker-compose.prod.yml`. Pointing `DATABASE_URL` at `:6432` without changing
Django `CONN_MAX_AGE` will break prepared statements in transaction pool mode.

Before enabling:

1. Set Django `CONN_MAX_AGE=0` (or use `pool_mode=session`).
2. Put roles in PgBouncer `userlist.txt` (not in git).
3. Keep `server_reset_query = DISCARD ALL`.
4. Soak on staging with `POSTGRES_RLS_ENABLED` at the **staging** default.
   Production RLS stays 0 until Human signs soak.
