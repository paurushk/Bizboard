#!/usr/bin/env bash
# Run the Postgres-only test lane locally (QOS-0006).
#
# The concurrency / row-lock tests are marked `@pytest.mark.postgres` and SKIP on
# SQLite, because SQLite does not meaningfully enforce `SELECT ... FOR UPDATE`.
# On a normal local run they are invisible, so an oversell / double-allocation
# regression only shows up in CI. Run this before pushing any change that touches
# allocation, stock movement, document numbering, or period close.
#
# Usage:
#   scripts/test_concurrency_local.sh                 # the whole postgres lane
#   scripts/test_concurrency_local.sh tests/test_concurrency_races.py
#   scripts/test_concurrency_local.sh -k numbering
#
# Requires Docker. Spins a throwaway postgres:17-alpine on a random free port,
# runs the lane, and tears the container down on exit (even on failure).
set -euo pipefail

cd "$(dirname "$0")/.."

CONTAINER="bizboard-pg-concurrency-$$"
PORT="$(python3 - <<'PY'
import socket
s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()
PY
)"

cleanup() { docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "starting postgres:17-alpine on 127.0.0.1:${PORT} ..."
docker run -d --name "$CONTAINER" \
  -e POSTGRES_DB=bizboard_concurrency \
  -e POSTGRES_USER=bizboard \
  -e POSTGRES_PASSWORD=bizboard \
  -p "127.0.0.1:${PORT}:5432" \
  postgres:17-alpine >/dev/null

echo -n "waiting for readiness"
for _ in $(seq 1 30); do
  if docker exec "$CONTAINER" pg_isready -U bizboard >/dev/null 2>&1; then echo " ok"; break; fi
  echo -n "."; sleep 1
done

export DATABASE_URL="postgresql://bizboard:bizboard@127.0.0.1:${PORT}/bizboard_concurrency"
export PYTEST_KEEP_DATABASE_URL=1   # settings_test drops DATABASE_URL locally unless this is set

ARGS=("$@")
if [ ${#ARGS[@]} -eq 0 ]; then ARGS=(-m postgres); fi

cd backend
PY_BIN=".venv/Scripts/python.exe"; [ -x "$PY_BIN" ] || PY_BIN=".venv/bin/python"; [ -x "$PY_BIN" ] || PY_BIN="python"
echo "running: $PY_BIN -m pytest ${ARGS[*]}"
exec "$PY_BIN" -m pytest "${ARGS[@]}" -p no:randomly -q
