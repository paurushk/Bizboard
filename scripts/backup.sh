#!/bin/sh
# BB-000253: Postgres dump helper for compose profile `backup`.
#
# A dump is a full multi-tenant PII / financial export, so this script is
# deliberately strict:
#   * FAIL CLOSED on encryption. Set BACKUP_GPG_RECIPIENT or BACKUP_AGE_RECIPIENT.
#     With neither set the script exits non-zero and writes nothing. The only way
#     to write a plaintext dump is BACKUP_ALLOW_UNENCRYPTED=1 (local dev / drills).
#   * A failed pg_dump is FATAL. /bin/sh has no `pipefail`, so the old
#     `pg_dump | gzip` pipeline reported success (and left a tiny valid gzip) when
#     pg_dump failed. The dump now goes to a temp file first and is checked.
#   * Optional OFFSITE copy: BACKUP_OFFSITE_CMD is run with the finished file as
#     "$1", e.g.  BACKUP_OFFSITE_CMD='rclone copyto "$1" r2:bizboard-backups/$(basename "$1")'
#     Set BACKUP_REQUIRE_OFFSITE=1 to make a missing/failed offsite copy fatal.
#   * Retention is by AGE (BACKUP_RETENTION_DAYS, default 30), never below the
#     newest BACKUP_MIN_KEEP (default 7) files, so a stalled job cannot silently
#     turn "14 dumps" into months of history or delete the only good copy.
#   * On success, ${BACKUP_DIR}/LAST_SUCCESS records the timestamp and file name.
#     scripts/check_backup_age.sh does not read that marker. It stats the newest
#     bizboard-*.gpg or *.age file (and *.sql.gz only when BACKUP_ALLOW_UNENCRYPTED=1)
#     and exits 1 when that mtime is older than 93600 seconds (26 hours).
set -eu
umask 077

BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
MIN_KEEP="${BACKUP_MIN_KEEP:-7}"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR" || true

BASE="${BACKUP_DIR}/bizboard-${STAMP}.sql.gz"
WORK_SQL="${BACKUP_DIR}/.bizboard-${STAMP}.sql.partial"
WORK_GZ="${BACKUP_DIR}/.bizboard-${STAMP}.sql.gz.partial"
WORK_ENC="${BACKUP_DIR}/.bizboard-${STAMP}.enc.partial"
trap 'rm -f "$WORK_SQL" "$WORK_GZ" "$WORK_ENC"' EXIT

fail() {
    echo "BACKUP FAILED: $*" >&2
    exit 1
}

# Decide the mode before touching the database.
MODE=""
if [ -n "${BACKUP_GPG_RECIPIENT:-}" ]; then
    MODE="gpg"
elif [ -n "${BACKUP_AGE_RECIPIENT:-}" ]; then
    MODE="age"
elif [ "${BACKUP_ALLOW_UNENCRYPTED:-0}" = "1" ]; then
    MODE="plain"
    echo "WARNING: BACKUP_ALLOW_UNENCRYPTED=1 — writing an UNENCRYPTED dump." >&2
else
    fail "no BACKUP_GPG_RECIPIENT / BACKUP_AGE_RECIPIENT set. Refusing to write a plaintext dump (set BACKUP_ALLOW_UNENCRYPTED=1 only for local dev)."
fi

if [ "$MODE" = "gpg" ] && ! command -v gpg >/dev/null 2>&1; then
    command -v apk >/dev/null 2>&1 && apk add --no-cache gnupg >/dev/null 2>&1 || true
    command -v gpg >/dev/null 2>&1 || fail "gpg is not installed and could not be added."
fi
if [ "$MODE" = "age" ] && ! command -v age >/dev/null 2>&1; then
    command -v apk >/dev/null 2>&1 && apk add --no-cache age >/dev/null 2>&1 || true
    command -v age >/dev/null 2>&1 || fail "age is not installed and could not be added."
fi

# 1. Dump (checked), 2. compress (verified).
# With row-level security forced, the app role must not dump (a non-superuser app role sees no rows,
# or the dump errors). Set BACKUP_DB_USER (and BACKUP_DB_PASSWORD) to a role that is a superuser or has
# BYPASSRLS. It falls back to POSTGRES_USER, which is the old behaviour.
if [ -n "${BACKUP_DB_PASSWORD:-}" ]; then PGPASSWORD="$BACKUP_DB_PASSWORD"; export PGPASSWORD; fi
pg_dump -h "${PGHOST:-db}" -U "${BACKUP_DB_USER:-${POSTGRES_USER}}" "${POSTGRES_DB}" > "$WORK_SQL" \
    || fail "pg_dump exited non-zero."
[ -s "$WORK_SQL" ] || fail "pg_dump produced an empty file."
gzip -c "$WORK_SQL" > "$WORK_GZ" || fail "gzip failed."
gzip -t "$WORK_GZ" || fail "compressed dump failed the gzip integrity test."
rm -f "$WORK_SQL"

# 3. Encrypt (or keep plain when explicitly allowed).
case "$MODE" in
    gpg)
        OUT="${BASE}.gpg"
        # GPG_BIN lets tests point at a stub. Production leaves it unset and uses gpg.
        if [ -n "${GPG_BIN:-}" ]; then
            sh "$GPG_BIN" --batch --yes --encrypt --recipient "${BACKUP_GPG_RECIPIENT}" --output "$WORK_ENC" "$WORK_GZ" \
                || fail "gpg encryption failed."
        else
            gpg --batch --yes --encrypt --recipient "${BACKUP_GPG_RECIPIENT}" --output "$WORK_ENC" "$WORK_GZ" \
                || fail "gpg encryption failed."
        fi
        ;;
    age)
        OUT="${BASE}.age"
        age -r "${BACKUP_AGE_RECIPIENT}" -o "$WORK_ENC" "$WORK_GZ" || fail "age encryption failed."
        ;;
    plain)
        OUT="$BASE"
        cp "$WORK_GZ" "$WORK_ENC"
        ;;
esac
[ -s "$WORK_ENC" ] || fail "final backup file is empty."
mv "$WORK_ENC" "$OUT"
chmod 600 "$OUT" || true
echo "Wrote ${OUT}"

# 4. Offsite copy.
if [ -n "${BACKUP_OFFSITE_CMD:-}" ]; then
    if sh -c "$BACKUP_OFFSITE_CMD" offsite "$OUT"; then
        echo "Offsite copy OK"
    else
        fail "offsite copy command failed (local file kept: ${OUT})."
    fi
elif [ "${BACKUP_REQUIRE_OFFSITE:-0}" = "1" ]; then
    fail "BACKUP_REQUIRE_OFFSITE=1 but BACKUP_OFFSITE_CMD is not set (local file kept: ${OUT})."
else
    echo "WARNING: no BACKUP_OFFSITE_CMD — this backup exists on this host only." >&2
fi

# 5. Mark success only after everything above passed.
printf '%s %s\n' "$STAMP" "$(basename "$OUT")" > "${BACKUP_DIR}/LAST_SUCCESS"

# 6. Retention by age, never below the newest MIN_KEEP files.
COUNT=0
for f in $(ls -1t "${BACKUP_DIR}"/bizboard-* 2>/dev/null || true); do
    COUNT=$((COUNT + 1))
    [ "$COUNT" -le "$MIN_KEEP" ] && continue
    if [ -n "$(find "$f" -mtime +"$RETENTION_DAYS" 2>/dev/null)" ]; then
        rm -f "$f"
        echo "Pruned ${f} (older than ${RETENTION_DAYS} days)"
    fi
done
