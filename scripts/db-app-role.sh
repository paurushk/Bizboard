#!/usr/bin/env bash
# SR0-06: create/refresh the non-superuser app role for any Compose environment.
#
# POSTGRES_USER (owner, superuser) bypasses FORCE ROW LEVEL SECURITY, so api/worker/beat
# must connect as a separate role that is NOSUPERUSER NOBYPASSRLS for RLS to be real.
# Idempotent: run it after every `migrate` and after every restore (new tables need the
# grants; default privileges also cover tables the owner creates later).
#
# Usage: scripts/db-app-role.sh <env-file> <compose-file>...
#   scripts/db-app-role.sh .env.staging docker-compose.yml docker-compose.staging.yml
#   scripts/db-app-role.sh .env docker-compose.yml docker-compose.prod.yml
set -euo pipefail
cd "$(dirname "$0")/.."
ENV_FILE="${1:?usage: db-app-role.sh <env-file> <compose-file>...}"
shift
[[ $# -gt 0 ]] || { echo "Give at least one compose file" >&2; exit 1; }
[[ -f "$ENV_FILE" ]] || { echo "Missing $ENV_FILE" >&2; exit 1; }

getv() { sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1 | tr -d '\r'; }
OWNER="$(getv POSTGRES_USER)"; DB="$(getv POSTGRES_DB)"
APP_USER="$(getv APP_DB_USER)"; APP_PW="$(getv APP_DB_PASSWORD)"
[[ -n "$OWNER" && -n "$DB" && -n "$APP_USER" && -n "$APP_PW" ]] \
  || { echo "POSTGRES_USER/POSTGRES_DB/APP_DB_USER/APP_DB_PASSWORD must be set in $ENV_FILE" >&2; exit 1; }
[[ "$APP_USER" != "$OWNER" ]] || { echo "APP_DB_USER must differ from POSTGRES_USER" >&2; exit 1; }

COMPOSE_ARGS=(--env-file "$ENV_FILE")
for f in "$@"; do COMPOSE_ARGS+=(-f "$f"); done

docker compose "${COMPOSE_ARGS[@]}" \
  exec -T db psql -v ON_ERROR_STOP=1 -U "$OWNER" -d "$DB" \
  -v app_user="$APP_USER" -v app_pw="$APP_PW" -v owner="$OWNER" -v dbname="$DB" \
  -f - < scripts/sql/app_role.sql
echo "App role '$APP_USER' ready (NOSUPERUSER NOBYPASSRLS)."
