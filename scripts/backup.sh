#!/bin/sh
# BB-000253: Postgres dump helper for compose profile `backup`.
# M1-013: a dump is a full multi-tenant PII / financial export. Encrypt it at
# rest when BACKUP_GPG_RECIPIENT (or BACKUP_AGE_RECIPIENT) is set, restrict the
# dir mode, and never write it anywhere git-tracked.
set -eu
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p /backups
chmod 700 /backups || true
PLAIN="/backups/bizboard-${STAMP}.sql.gz"

if [ -n "${BACKUP_GPG_RECIPIENT:-}" ] && command -v gpg >/dev/null 2>&1; then
    OUT="${PLAIN}.gpg"
    pg_dump -h db -U "${POSTGRES_USER}" "${POSTGRES_DB}" | gzip \
        | gpg --batch --yes --encrypt --recipient "${BACKUP_GPG_RECIPIENT}" --output "${OUT}"
elif [ -n "${BACKUP_AGE_RECIPIENT:-}" ] && command -v age >/dev/null 2>&1; then
    OUT="${PLAIN}.age"
    pg_dump -h db -U "${POSTGRES_USER}" "${POSTGRES_DB}" | gzip \
        | age -r "${BACKUP_AGE_RECIPIENT}" -o "${OUT}"
else
    echo "WARNING: BACKUP_GPG_RECIPIENT / BACKUP_AGE_RECIPIENT unset — writing an UNENCRYPTED dump." >&2
    OUT="${PLAIN}"
    pg_dump -h db -U "${POSTGRES_USER}" "${POSTGRES_DB}" | gzip > "${OUT}"
fi
chmod 600 "${OUT}" || true
echo "Wrote ${OUT}"
# Keep last 14 dumps (any extension)
ls -1t /backups/bizboard-* 2>/dev/null | tail -n +15 | xargs -r rm -f
