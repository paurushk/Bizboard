#!/usr/bin/env bash
# Fast full backend run on Postgres.
#
# Why it is fast: (1) the database lives in RAM with fsync off (tests need no durability),
# (2) migrations run ONCE into a template database, (3) that template is cloned per
# pytest-xdist worker (a copy takes seconds, migrating takes minutes), (4) workers run in parallel.
#
# Usage:   scripts/pytest_pg_fast.sh [pytest args...]        (default: the CI marker set)
# Env:     WORKERS=8 (default: CPU count, max 8)   REBUILD=1 (re-migrate the template)
#          KEEP=1 (leave the container up for the next run; it is reused)
set -euo pipefail

cd "$(dirname "$0")/../backend"
NAME=bb-pg-fast
PORT=${PG_PORT:-55433}
WORKERS=${WORKERS:-$(python -c "import os;print(min(8, os.cpu_count() or 4))")}
export PYTEST_KEEP_DATABASE_URL=1 CI=1
export DATABASE_URL="postgres://postgres:pw@127.0.0.1:${PORT}/bb"
unset PYTHONPATH || true

psql_exec() { docker exec "$NAME" psql -U postgres -v ON_ERROR_STOP=1 -qAt "$@"; }

if ! docker ps --format '{{.Names}}' | grep -qx "$NAME"; then
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  docker run -d --name "$NAME" -e POSTGRES_PASSWORD=pw -e POSTGRES_DB=bb -p "${PORT}:5432" \
    --tmpfs /var/lib/postgresql/data:rw,size=3g \
    postgres:17-alpine \
    -c fsync=off -c synchronous_commit=off -c full_page_writes=off \
    -c max_connections=300 -c shared_buffers=512MB -c max_wal_size=2GB >/dev/null
  for _ in $(seq 1 30); do docker exec "$NAME" pg_isready -U postgres -q && break; sleep 1; done
  REBUILD=1
fi

if [ "${REBUILD:-0}" = "1" ] || [ -z "$(psql_exec -d postgres -c "select 1 from pg_database where datname='test_bb'")" ]; then
  echo ">> building the migrated template database (once)"
  python -m pytest -p no:randomly -q --create-db tests/test_auth.py -k "register_existing_email_same_shape" -x >/dev/null || true
fi

echo ">> cloning the template for ${WORKERS} workers"
for i in $(seq 0 $((WORKERS - 1))); do
  psql_exec -d postgres -c "DROP DATABASE IF EXISTS test_bb_gw${i}" >/dev/null
  psql_exec -d postgres -c "CREATE DATABASE test_bb_gw${i} TEMPLATE test_bb" >/dev/null
done

if [ "$#" -eq 0 ]; then
  set -- -m "not flaky_quarantine and not slow and not llm_accuracy"
fi
echo ">> running"
python -m pytest -n "$WORKERS" --dist=loadfile -p no:randomly -q --tb=short --reuse-db "$@"
rc=$?

[ "${KEEP:-0}" = "1" ] || docker rm -f "$NAME" >/dev/null 2>&1 || true
exit $rc
