"""Sprint B: RLS for new tenant tables (lead activities)."""

from django.db import migrations

EXTRA_TABLES = [
    "crm_leadactivity",
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
        ("core", "0010_sprint3_document_series_gstin_fy"),
        ("crm", "0002_sprint_b_lead_activity"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
