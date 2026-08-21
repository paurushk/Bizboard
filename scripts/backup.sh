#!/bin/sh
# BB-000253: Postgres dump helper for compose profile `backup`.
set -eu
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT="/backups/bizboard-${STAMP}.sql.gz"
mkdir -p /backups
pg_dump -h db -U "${POSTGRES_USER}" "${POSTGRES_DB}" | gzip > "${OUT}"
echo "Wrote ${OUT}"
# Keep last 14 dumps
ls -1t /backups/bizboard-*.sql.gz 2>/dev/null | tail -n +15 | xargs -r rm -f
