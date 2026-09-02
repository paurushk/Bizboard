"""SYS-01: every tenant table must be covered by the RLS rollout migration,
and (on Postgres) must actually carry the isolation policy with FORCE RLS.
"""

import importlib

import pytest
from django.apps import apps
from django.db import connection

pytestmark = pytest.mark.django_db

# Tables intentionally left out of RLS (read during tenant resolution).
_EXCLUDED = {"accounts_companyuser", "accounts_companygstin"}


def _tenant_tables() -> set[str]:
    out = set()
    for model in apps.get_models():
        try:
            field = model._meta.get_field("company")
        except Exception:  # noqa: BLE001
            continue
        if getattr(field, "many_to_one", False):
            out.add(model._meta.db_table)
    return out


def _migration_tables() -> set[str]:
    mod = importlib.import_module("core.migrations.0020_rls_all_tenant_tables")
    return set(mod.RLS_TABLES)


def test_every_tenant_table_is_in_the_rls_migration():
    tenant = _tenant_tables() - _EXCLUDED
    covered = _migration_tables()
    missing = sorted(tenant - covered)
    assert not missing, (
        "These tenant (`company` FK) tables have no RLS policy in "
        "core/migrations/0020_rls_all_tenant_tables.py — add them (or, if they "
        "are read during tenant resolution, add to _EXCLUDED here): " + ", ".join(missing)
    )


def test_rls_migration_lists_no_unknown_tables():
    covered = _migration_tables()
    known = {m._meta.db_table for m in apps.get_models()}
    unknown = sorted(covered - known)
    assert not unknown, f"RLS migration references non-existent tables: {unknown}"


@pytest.mark.postgres
def test_rls_policy_present_and_forced_on_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("RLS is a Postgres feature")
    with connection.cursor() as cur:
        cur.execute(
            "SELECT c.relname FROM pg_class c "
            "WHERE c.relrowsecurity AND c.relforcerowsecurity"
        )
        forced = {r[0] for r in cur.fetchall()}
        cur.execute(
            "SELECT tablename FROM pg_policies WHERE policyname = 'bizboard_company_isolation'"
        )
        with_policy = {r[0] for r in cur.fetchall()}
    for tbl in _migration_tables():
        assert tbl in forced, f"{tbl} does not have FORCE ROW LEVEL SECURITY"
        assert tbl in with_policy, f"{tbl} is missing the bizboard_company_isolation policy"
