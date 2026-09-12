#!/usr/bin/env bash
# QOS-0022 — exercise the real backup/restore pipeline on a schedule, not just
# the logic (that's covered by tests/errors/test_backup_restore_drill.py at the
# Django-ORM layer). This drives the same pg_dump/gzip -> psql restore path as
# scripts/backup.sh / scripts/restore.sh, but into a throwaway scratch DB —
# never the live one — then runs the standalone invariant sweep
# (manage.py check_invariants) against the restored data and fails loudly if
# anything is inconsistent.
#
# Usage:
#   scripts/restore_drill.sh
#
# Requires Docker. Spins up two throwaway postgres:17-alpine containers
# (source + scratch) on random free ports and tears both down on exit, even
# on failure. Exit code is the drill's pass/fail signal — wire it into a
# scheduled job (cron / CI) and alert on non-zero.
set -euo pipefail

cd "$(dirname "$0")/.."

RUN_ID="$$"
SRC_CONTAINER="bizboard-pg-drill-src-${RUN_ID}"
DST_CONTAINER="bizboard-pg-drill-dst-${RUN_ID}"
DUMP_FILE="$(mktemp -u)-bizboard-drill.sql.gz"

free_port() {
  # Prefer `python` — on Windows, `python3` is often a Microsoft Store shim
  # that exists on PATH but errors out rather than running.
  local py="python"; command -v python >/dev/null 2>&1 || py="python3"
  "$py" - <<'PY'
import socket
s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()
PY
}

SRC_PORT="$(free_port)"
DST_PORT="$(free_port)"

cleanup() {
  docker rm -f "$SRC_CONTAINER" "$DST_CONTAINER" >/dev/null 2>&1 || true
  rm -f "$DUMP_FILE" 2>/dev/null || true
}
trap cleanup EXIT

wait_ready() {
  local container="$1"
  for _ in $(seq 1 30); do
    if docker exec "$container" pg_isready -U bizboard >/dev/null 2>&1; then return 0; fi
    sleep 1
  done
  echo "restore-drill: $container never became ready" >&2
  return 1
}

echo "restore-drill: starting source db on 127.0.0.1:${SRC_PORT} ..."
docker run -d --name "$SRC_CONTAINER" \
  -e POSTGRES_DB=bizboard_drill_src -e POSTGRES_USER=bizboard -e POSTGRES_PASSWORD=bizboard \
  -p "127.0.0.1:${SRC_PORT}:5432" postgres:17-alpine >/dev/null
wait_ready "$SRC_CONTAINER"

echo "restore-drill: migrating + seeding the source db ..."
export DATABASE_URL="postgresql://bizboard:bizboard@127.0.0.1:${SRC_PORT}/bizboard_drill_src"
export PYTEST_KEEP_DATABASE_URL=1
export DJANGO_SETTINGS_MODULE=config.settings_test
PY_BIN="$(pwd)/backend/.venv/Scripts/python.exe"; [ -x "$PY_BIN" ] || PY_BIN="$(pwd)/backend/.venv/bin/python"; [ -x "$PY_BIN" ] || PY_BIN="python"
(cd backend && "$PY_BIN" manage.py migrate --noinput)
(cd backend && DEBUG=1 "$PY_BIN" manage.py seed_demo)

echo "restore-drill: dumping source db (same pipeline as scripts/backup.sh) ..."
docker exec "$SRC_CONTAINER" pg_dump -U bizboard bizboard_drill_src | gzip > "$DUMP_FILE"
[ -s "$DUMP_FILE" ] || { echo "restore-drill: dump is empty" >&2; exit 1; }

echo "restore-drill: starting scratch db on 127.0.0.1:${DST_PORT} ..."
docker run -d --name "$DST_CONTAINER" \
  -e POSTGRES_DB=bizboard_drill_scratch -e POSTGRES_USER=bizboard -e POSTGRES_PASSWORD=bizboard \
  -p "127.0.0.1:${DST_PORT}:5432" postgres:17-alpine >/dev/null
wait_ready "$DST_CONTAINER"

echo "restore-drill: restoring dump into the scratch db (same pipeline as scripts/restore.sh) ..."
gunzip -c "$DUMP_FILE" | docker exec -i "$DST_CONTAINER" psql -U bizboard -d bizboard_drill_scratch -v ON_ERROR_STOP=1 >/dev/null

echo "restore-drill: running the invariant sweep against the restored scratch db ..."
export DATABASE_URL="postgresql://bizboard:bizboard@127.0.0.1:${DST_PORT}/bizboard_drill_scratch"
(cd backend && "$PY_BIN" manage.py check_invariants)

echo "restore-drill: PASS — restored data is invariant-clean."
