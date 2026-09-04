"""B6-021: assert the configured DB role can't silently bypass RLS.

`core/migrations/0020_rls_all_tenant_tables.py` uses `FORCE ROW LEVEL
SECURITY`, which still lets two things through unconditionally: a Postgres
**superuser** connection, and any role granted **BYPASSRLS**. Nothing
previously asserted that the app's configured `DATABASES["default"]` role
lacks both attributes — a misconfigured connection (e.g. one that
accidentally points at the Postgres superuser, common in some managed-DB
default setups) would make every RLS policy in the codebase a silent no-op
for that process, with no error anywhere.
"""

from django.core.checks import Tags, Warning, register
from django.db import connections


@register(Tags.security, Tags.database)
def check_rls_role_privileges(app_configs, **kwargs):
    errors = []
    connection = connections["default"]
    # RLS (and this check) only applies to Postgres — SQLite (local/CI
    # tests) makes RLS a no-op already and has no pg_roles to query.
    if connection.vendor != "postgresql":
        return errors
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
            row = cursor.fetchone()
    except Exception:
        # Don't fail unrelated management commands (a fresh/unmigrated DB,
        # one that's briefly unreachable, restricted permissions on
        # pg_roles, etc.) just because this check couldn't run.
        return errors
    if not row:
        return errors
    rolsuper, rolbypassrls = row
    if rolsuper:
        errors.append(
            Warning(
                "The configured database role is a Postgres SUPERUSER — row-level "
                "security policies are silently bypassed for superuser connections, "
                "defeating the tenant-isolation backstop RLS is meant to provide.",
                hint="Use a non-superuser role for DATABASES['default'] in production.",
                id="core.W001",
            )
        )
    if rolbypassrls:
        errors.append(
            Warning(
                "The configured database role has BYPASSRLS — row-level security "
                "policies are silently bypassed for this role, defeating the "
                "tenant-isolation backstop RLS is meant to provide.",
                hint="Revoke BYPASSRLS from the app's database role: ALTER ROLE <role> NOBYPASSRLS;",
                id="core.W002",
            )
        )
    return errors
