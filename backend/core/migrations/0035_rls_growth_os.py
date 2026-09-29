"""Enroll Growth OS tables in tenant RLS."""

from django.db import migrations

RLS_TABLES = [
    "core_sequencecounter",
    "crm_campaign",
    "crm_opportunityline",
    "crm_referralcode",
    "crm_referralreward",
    "complaints_complaint",
    "complaints_complaintattachment",
    "support_ticket",
    "support_ticketcomment",
    "support_ticketattachment",
    "contracts_contract",
    "contracts_contractserviceevent",
    "contracts_contractdocument",
]

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
        ("core", "0034_growth_os"),
        ("crm", "0008_growth_os"),
        ("complaints", "0001_growth_os"),
        ("support", "0001_growth_os"),
        ("contracts", "0002_growth_os"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
