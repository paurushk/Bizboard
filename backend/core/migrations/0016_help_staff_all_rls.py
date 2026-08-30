"""Allow staff help-health ?all=1 to read across tenants when RLS is on.

Writes stay company-scoped (WITH CHECK unchanged). The view sets
app.help_staff_all = '1' only for is_staff + ?all=1.
"""

from django.db import migrations

HELP_RLS_TABLES = [
    "core_helpevent",
    "core_helpfeedback",
]


def enable_staff_all_policy(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    tables_sql = ",\n    ".join(f"'{t}'" for t in HELP_RLS_TABLES)
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
      EXECUTE format(
        'CREATE POLICY bizboard_company_isolation ON %I
         USING (
           company_id::text = NULLIF(current_setting(''app.company_id'', true), '''')
           OR NULLIF(current_setting(''app.help_staff_all'', true), '''') = ''1''
         )
         WITH CHECK (company_id::text = NULLIF(current_setting(''app.company_id'', true), ''''))',
        tbl
      );
    EXCEPTION WHEN undefined_table THEN
      NULL;
    WHEN undefined_object THEN
      NULL;
    END;
  END LOOP;
END $$;
"""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(sql)


def revert_staff_all_policy(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    tables_sql = ",\n    ".join(f"'{t}'" for t in HELP_RLS_TABLES)
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
      EXECUTE format(
        'CREATE POLICY bizboard_company_isolation ON %I
         USING (company_id::text = NULLIF(current_setting(''app.company_id'', true), ''''))
         WITH CHECK (company_id::text = NULLIF(current_setting(''app.company_id'', true), ''''))',
        tbl
      );
    EXCEPTION WHEN undefined_table THEN
      NULL;
    WHEN undefined_object THEN
      NULL;
    END;
  END LOOP;
END $$;
"""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(sql)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0015_help_event_feedback"),
    ]

    operations = [
        migrations.RunPython(enable_staff_all_policy, revert_staff_all_policy),
    ]
