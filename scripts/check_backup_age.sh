#!/bin/sh
# Exit 1 when the newest encrypted dump is older than 26 hours.
# Point BACKUP_DIR at the directory backup.sh writes (default /backups).
set -eu
DIR="${BACKUP_DIR:-/backups}"
# Encrypted dumps only, unless BACKUP_ALLOW_UNENCRYPTED=1 (local dev / drills).
PATTERNS="$DIR/bizboard-*.gpg $DIR/bizboard-*.age"
[ "${BACKUP_ALLOW_UNENCRYPTED:-0}" = "1" ] && PATTERNS="$PATTERNS $DIR/bizboard-*.sql.gz"
# shellcheck disable=SC2086
NEWEST=$(ls -1t $PATTERNS 2>/dev/null | head -n 1 || true)
if [ -z "$NEWEST" ] || [ ! -f "$NEWEST" ]; then
    echo "ERROR: no encrypted backup in ${DIR}" >&2
    exit 1
fi
# GNU date. The compose backup container is Debian/Alpine with date -d or stat.
NOW=$(date +%s)
THEN=$(stat -c %Y "$NEWEST" 2>/dev/null || stat -f %m "$NEWEST")
AGE=$((NOW - THEN))
if [ "$AGE" -gt 93600 ]; then
    echo "ERROR: ${NEWEST} is ${AGE}s old (limit 93600s / 26h)" >&2
    exit 1
fi
echo "OK ${NEWEST} age=${AGE}s"
