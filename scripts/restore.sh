#!/bin/sh
# Wave 16A: restore latest (or named) backup into Postgres.
# Usage (compose profile restore):
#   docker compose --profile restore run --rm restore
# Optional: RESTORE_FILE=/backups/bizboard-YYYYMMDD....sql.gz
set -eu
BACKUPS_DIR="${BACKUPS_DIR:-/backups}"
if [ -n "${RESTORE_FILE:-}" ]; then
  SRC="${RESTORE_FILE}"
else
  SRC=$(ls -1t "${BACKUPS_DIR}"/bizboard-*.sql.gz 2>/dev/null | head -n 1 || true)
fi
if [ -z "${SRC}" ] || [ ! -f "${SRC}" ]; then
  echo "No backup found in ${BACKUPS_DIR}. Run backup profile first." >&2
  exit 1
fi
echo "Restoring ${SRC} into ${POSTGRES_DB}@db ..."
# Drop connections and recreate public schema carefully — pilot restore only.
gunzip -c "${SRC}" | psql -h db -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1
echo "Restore complete from ${SRC}"
echo "RPO: last successful backup timestamp in filename. RTO: restore duration + migrate check."
