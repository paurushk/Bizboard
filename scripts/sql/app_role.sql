-- SR0-06: the non-superuser app role (NOSUPERUSER NOBYPASSRLS) and its grants.
-- psql variables: app_user, app_pw, owner, dbname. Idempotent.
-- Used by scripts/db-app-role.sh (Compose hosts) and the CI RLS lane (.github/workflows/ci.yml).
SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE', :'app_user')
  WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user') \gexec
SELECT format('ALTER ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE', :'app_user', :'app_pw') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'dbname', :'app_user') \gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'app_user') \gexec
SELECT format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO %I', :'app_user') \gexec
SELECT format('GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO %I', :'app_user') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I', :'owner', :'app_user') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO %I', :'owner', :'app_user') \gexec
-- WP-5: the timeouts live on the role, so they hold through PgBouncer too. PgBouncer accepts the
-- libpq startup `options` (ignore_startup_parameters) but does not pass it on, so the
-- `-c statement_timeout=...` string in config/settings.py only reaches direct connections.
-- Keep these equal to BB-000546 in settings.py.
SELECT format('ALTER ROLE %I SET statement_timeout = %L', :'app_user', '30s') \gexec
SELECT format('ALTER ROLE %I SET idle_in_transaction_session_timeout = %L', :'app_user', '60s') \gexec

-- WP-5 PgBouncer auth_query (only when pgb_pw is passed). PgBouncer signs in as pgbouncer_auth,
-- which can do one thing: call pgbouncer.user_lookup() to fetch the SCRAM verifier of a
-- non-superuser login role. No app password or verifier is written to disk; superusers (the owner
-- used by migrate/backup) cannot sign in through the pool.
\if :{?pgb_pw}
SELECT 'CREATE ROLE pgbouncer_auth LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE'
  WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pgbouncer_auth') \gexec
SELECT format('ALTER ROLE pgbouncer_auth LOGIN PASSWORD %L NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE', :'pgb_pw') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO pgbouncer_auth', :'dbname') \gexec
CREATE SCHEMA IF NOT EXISTS pgbouncer;
REVOKE ALL ON SCHEMA pgbouncer FROM PUBLIC;
GRANT USAGE ON SCHEMA pgbouncer TO pgbouncer_auth;
CREATE OR REPLACE FUNCTION pgbouncer.user_lookup(p_user text, OUT uname text, OUT phash text)
  RETURNS record LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog AS
  $$ SELECT usename::text, passwd::text FROM pg_catalog.pg_shadow
     WHERE usename = p_user AND NOT usesuper AND usename <> 'pgbouncer_auth' $$;
REVOKE ALL ON FUNCTION pgbouncer.user_lookup(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pgbouncer.user_lookup(text) TO pgbouncer_auth;
\endif
SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname IN (:'owner', :'app_user') ORDER BY 1;
