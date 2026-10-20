#!/usr/bin/env bash
# STG-17: create/refresh the non-superuser app role used by the STAGING api/worker/beat.
#
# POSTGRES_USER (owner, superuser) bypasses FORCE ROW LEVEL SECURITY, so the app must
# connect as a separate role that is NOSUPERUSER NOBYPASSRLS for RLS to be real.
# Idempotent: run it after every `migrate` (new tables need the grants; default
# privileges below also cover tables the owner creates later).
#
# Usage: scripts/staging-db-role.sh        (needs the staging `db` service running)
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -f .env.staging ]] || { echo "Missing .env.staging" >&2; exit 1; }

getv() { sed -n "s/^$1=//p" .env.staging | tail -n 1 | tr -d '\r'; }
OWNER="$(getv POSTGRES_USER)"; DB="$(getv POSTGRES_DB)"
APP_USER="$(getv APP_DB_USER)"; APP_PW="$(getv APP_DB_PASSWORD)"
[[ -n "$OWNER" && -n "$DB" && -n "$APP_USER" && -n "$APP_PW" ]] \
  || { echo "POSTGRES_USER/POSTGRES_DB/APP_DB_USER/APP_DB_PASSWORD must be set in .env.staging" >&2; exit 1; }
[[ "$APP_USER" != "$OWNER" ]] || { echo "APP_DB_USER must differ from POSTGRES_USER" >&2; exit 1; }

docker compose --env-file .env.staging -f docker-compose.yml -f docker-compose.staging.yml \
  exec -T db psql -v ON_ERROR_STOP=1 -U "$OWNER" -d "$DB" \
  -v app_user="$APP_USER" -v app_pw="$APP_PW" -v owner="$OWNER" -v dbname="$DB" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE', :'app_user')
  WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user') \gexec
SELECT format('ALTER ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE', :'app_user', :'app_pw') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'dbname', :'app_user') \gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'app_user') \gexec
SELECT format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO %I', :'app_user') \gexec
SELECT format('GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO %I', :'app_user') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I', :'owner', :'app_user') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO %I', :'owner', :'app_user') \gexec
SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname IN (:'owner', :'app_user') ORDER BY 1;
SQL
echo "App role '$APP_USER' ready (NOSUPERUSER NOBYPASSRLS)."
