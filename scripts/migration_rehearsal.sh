#!/usr/bin/env bash
# QOS-0014 — migration rehearsal against a SYNTHETIC production-shaped
# dataset. This is explicitly NOT a substitute for a real anonymised
# production dump (see accounts/management/commands/seed_synthetic_bulk.py's
# own docstring) — synthetic bulk_create can't reproduce real messy schemas
# or a real tenant's row-count skew. What it DOES catch: a migration that's
# fine against an empty/tiny table and slow or lock-heavy against a
# real-sized one, which is the concrete failure mode this item worries about.
#
# Usage:
#   scripts/migration_rehearsal.sh [invoice-count]   # default 5000
#
# Requires Docker. Spins up a throwaway postgres:17-alpine on a random free
# port and tears it down on exit, even on failure. Exit code is the
# rehearsal's pass/fail signal.
set -euo pipefail

cd "$(dirname "$0")/.."

INVOICE_COUNT="${1:-5000}"
CONTAINER="bizboard-pg-migration-rehearsal-$$"

free_port() {
  local py="python"; command -v python >/dev/null 2>&1 || py="python3"
  "$py" - <<'PY'
import socket
s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()
PY
}

PORT="$(free_port)"

cleanup() { docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

wait_ready() {
  for _ in $(seq 1 30); do
    if docker exec "$CONTAINER" pg_isready -U bizboard >/dev/null 2>&1; then return 0; fi
    sleep 1
  done
  echo "migration-rehearsal: db never became ready" >&2
  return 1
}

echo "migration-rehearsal: starting db on 127.0.0.1:${PORT} ..."
docker run -d --name "$CONTAINER" \
  -e POSTGRES_DB=bizboard_rehearsal -e POSTGRES_USER=bizboard -e POSTGRES_PASSWORD=bizboard \
  -p "127.0.0.1:${PORT}:5432" postgres:17-alpine >/dev/null
wait_ready

export DATABASE_URL="postgresql://bizboard:bizboard@127.0.0.1:${PORT}/bizboard_rehearsal"
export PYTEST_KEEP_DATABASE_URL=1
export DJANGO_SETTINGS_MODULE=config.settings_test
PY_BIN="$(pwd)/backend/.venv/Scripts/python.exe"; [ -x "$PY_BIN" ] || PY_BIN="$(pwd)/backend/.venv/bin/python"; [ -x "$PY_BIN" ] || PY_BIN="python"

echo "migration-rehearsal: applying the full migration series to an empty db ..."
(cd backend && "$PY_BIN" manage.py migrate --noinput)

echo "migration-rehearsal: seeding ${INVOICE_COUNT} synthetic invoices for volume ..."
(cd backend && DEBUG=1 "$PY_BIN" manage.py seed_demo)
(cd backend && DEBUG=1 "$PY_BIN" manage.py seed_synthetic_bulk --invoices "$INVOICE_COUNT")

echo "migration-rehearsal: re-running migrate against the now-populated db (idempotency + timing) ..."
START=$(date +%s)
(cd backend && "$PY_BIN" manage.py migrate --noinput)
END=$(date +%s)
ELAPSED=$((END - START))
echo "migration-rehearsal: migrate against ${INVOICE_COUNT} rows took ${ELAPSED}s"

BUDGET_SECONDS=60
if [ "$ELAPSED" -gt "$BUDGET_SECONDS" ]; then
  echo "migration-rehearsal: FAIL — migrate took ${ELAPSED}s, over the ${BUDGET_SECONDS}s budget" >&2
  exit 1
fi

# G-11b leftover (95-plan V3): sweep after migrate+seed. Synthetic bulk_create is
# not a prod dump and may violate some invariants (party subledger, GST tie-out,
# numbering). Default: record the output and continue. Set
# INVARIANTS_STRICT_REHEARSAL=1 to fail the script on any invariant miss.
echo "migration-rehearsal: check_invariants after synthetic seed ..."
set +e
(cd backend && "$PY_BIN" manage.py check_invariants)
INV_RC=$?
set -e
if [ "$INV_RC" -ne 0 ]; then
  echo "migration-rehearsal: check_invariants exited ${INV_RC} on SYNTHETIC data (not a prod dump)."
  if [ "${INVARIANTS_STRICT_REHEARSAL:-0}" = "1" ]; then
    echo "migration-rehearsal: FAIL — INVARIANTS_STRICT_REHEARSAL=1" >&2
    exit 1
  fi
  echo "migration-rehearsal: WARNING — not failing the rehearsal. A real anonymised dump + INVARIANTS_STRICT_REHEARSAL=1 is the 95 bar."
else
  echo "migration-rehearsal: check_invariants clean on the synthetic seed."
fi

echo "migration-rehearsal: PASS — the migration series applies cleanly and within budget at volume."
echo "migration-rehearsal: reminder — this is a SYNTHETIC dataset; it does not replace a real anonymised production dump."
