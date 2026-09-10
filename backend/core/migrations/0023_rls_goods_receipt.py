"""RLS coverage follow-up: `purchases.GoodsReceipt` / `GoodsReceiptItem` (GRN,
FR-018) each carry a `company` FK but were added to the codebase in
purchases/migrations/0034 — after 0020_rls_all_tenant_tables.py ran — so they
were never enrolled. `tests/test_rls_coverage.py` flags any tenant (`company`
FK) table missing from the RLS policy set. Same idempotent, Postgres-only,
no-op-on-SQLite pattern as 0020 / 0022; both tables scope to the operating
company like every other purchase document.
"""

from django.db import migrations

RLS_TABLES = ["purchases_goodsreceipt", "purchases_goodsreceiptitem"]

_POLICY = "bizboard_company_isolation"

ENABLE_SQL = r"""
DO $$
DECLARE
  tbl text;
BEGIN
  FOREACH tbl IN ARRAY %(tables)s
  LOOP
    BEGIN
      EXECUTE format('ALTER TABLE %%I ENABLE ROW LEVEL SECURITY', tbl);
      EXECUTE format('ALTER TABLE %%I FORCE ROW LEVEL SECURITY', tbl);
      EXECUTE format('DROP POLICY IF EXISTS %(policy)s ON %%I', tbl);
      EXECUTE format(
        'CREATE POLICY %(policy)s ON %%I
           USING (
             company_id::text = NULLIF(current_setting(''app.company_id'', true), '''')
             OR current_setting(''app.rls_bypass'', true) = ''1''
           )
           WITH CHECK (
             company_id::text = NULLIF(current_setting(''app.company_id'', true), '''')
             OR current_setting(''app.rls_bypass'', true) = ''1''
           )',
        tbl
      );
    EXCEPTION WHEN undefined_table THEN
      NULL;
    END;
  END LOOP;
END $$;
""" % {
    "tables": "ARRAY[" + ",".join(f"'{t}'" for t in RLS_TABLES) + "]",
    "policy": _POLICY,
}

DISABLE_SQL = r"""
DO $$
DECLARE
  tbl text;
BEGIN
  FOREACH tbl IN ARRAY %(tables)s
  LOOP
    BEGIN
      EXECUTE format('DROP POLICY IF EXISTS %(policy)s ON %%I', tbl);
      EXECUTE format('ALTER TABLE %%I NO FORCE ROW LEVEL SECURITY', tbl);
      EXECUTE format('ALTER TABLE %%I DISABLE ROW LEVEL SECURITY', tbl);
    EXCEPTION WHEN undefined_table THEN
      NULL;
    END;
  END LOOP;
END $$;
""" % {
    "tables": "ARRAY[" + ",".join(f"'{t}'" for t in RLS_TABLES) + "]",
    "policy": _POLICY,
}


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(ENABLE_SQL)


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(DISABLE_SQL)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0022_rls_processed_webhook_event"),
        ("purchases", "0034_goodsreceipt_goodsreceiptitem_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
