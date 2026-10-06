#!/bin/sh
# Wave 16A: restore latest (or named) backup into Postgres.
# Usage (compose profile restore):
#   docker compose --profile restore run --rm restore
# Optional: RESTORE_FILE=/backups/bizboard-YYYYMMDD....sql.gz[.gpg|.age]
#
# Encrypted dumps (what scripts/backup.sh writes by default) are decrypted on the
# fly: .gpg uses the keyring in the restore container; .age needs
# RESTORE_AGE_IDENTITY=/path/to/identity.txt.
set -eu
BACKUPS_DIR="${BACKUPS_DIR:-/backups}"
if [ -n "${RESTORE_FILE:-}" ]; then
  SRC="${RESTORE_FILE}"
else
  SRC=$(ls -1t "${BACKUPS_DIR}"/bizboard-*.sql.gz "${BACKUPS_DIR}"/bizboard-*.sql.gz.gpg \
        "${BACKUPS_DIR}"/bizboard-*.sql.gz.age 2>/dev/null | head -n 1 || true)
fi
if [ -z "${SRC}" ] || [ ! -f "${SRC}" ]; then
  echo "No backup found in ${BACKUPS_DIR}. Run backup profile first." >&2
  exit 1
fi

decrypt() {
  case "$SRC" in
    *.gpg)
      if [ -n "${GPG_BIN:-}" ]; then sh "$GPG_BIN" --batch --decrypt "$SRC"; else gpg --batch --decrypt "$SRC"; fi
      ;;
    *.age)
      [ -n "${RESTORE_AGE_IDENTITY:-}" ] || { echo "RESTORE_AGE_IDENTITY is required for .age dumps" >&2; exit 1; }
      age -d -i "$RESTORE_AGE_IDENTITY" "$SRC" ;;
    *) cat "$SRC" ;;
  esac
}

# A truncated or corrupt dump must stop here, not feed half a schema to psql.
TMP_GZ="$(mktemp)"
trap 'rm -f "$TMP_GZ"' EXIT
decrypt > "$TMP_GZ" || { echo "Could not read/decrypt ${SRC}" >&2; exit 1; }
gzip -t "$TMP_GZ" || { echo "${SRC} failed the gzip integrity test; refusing to restore." >&2; exit 1; }

echo "Restoring ${SRC} into ${POSTGRES_DB}@db ..."
# Drop connections and recreate public schema carefully — pilot restore only.
gunzip -c "$TMP_GZ" | psql -h db -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1
echo "Restore complete from ${SRC}"
echo "RPO: last successful backup timestamp in filename. RTO: restore duration + migrate check."
