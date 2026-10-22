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
SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname IN (:'owner', :'app_user') ORDER BY 1;
