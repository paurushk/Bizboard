"""FORCE RLS on GatewayRefundOutbox and DunningReminder (N-085)."""

from django.db import migrations

EXTRA_TABLES = [
    "payments_gatewayrefundoutbox",
    "payments_dunningreminder",
]


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    tables_sql = ",\n    ".join(f"'{t}'" for t in EXTRA_TABLES)
    sql = f"""
DO $$
DECLARE
  tbl text;
BEGIN
  FOREACH tbl IN ARRAY ARRAY[
    {tables_sql}
  ]
  LOOP
    BEGIN
      EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', tbl);
      EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', tbl);
      EXECUTE format('DROP POLICY IF EXISTS bizboard_company_isolation ON %I', tbl);
      EXECUTE format(
        'CREATE POLICY bizboard_company_isolation ON %I
         USING (company_id::text = NULLIF(current_setting(''app.company_id'', true), ''''))
         WITH CHECK (company_id::text = NULLIF(current_setting(''app.company_id'', true), ''''))',
        tbl
      );
    EXCEPTION WHEN undefined_table THEN
      NULL;
    WHEN undefined_column THEN
      NULL;
    END;
  END LOOP;
END $$;
"""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(sql)


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    tables_sql = ",\n    ".join(f"'{t}'" for t in EXTRA_TABLES)
    sql = f"""
DO $$
DECLARE
  tbl text;
BEGIN
  FOREACH tbl IN ARRAY ARRAY[
    {tables_sql}
  ]
  LOOP
    BEGIN
      EXECUTE format('DROP POLICY IF EXISTS bizboard_company_isolation ON %I', tbl);
      EXECUTE format('ALTER TABLE %I DISABLE ROW LEVEL SECURITY', tbl);
    EXCEPTION WHEN undefined_table THEN
      NULL;
    END;
  END LOOP;
END $$;
"""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(sql)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0017_auditevent_action_len"),
        ("payments", "0019_recon_match_unique"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
