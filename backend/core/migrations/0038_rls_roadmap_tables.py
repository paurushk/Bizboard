"""Enroll roadmap tenant tables in Postgres RLS."""

from django.db import migrations

RLS_TABLES = [
    "workshop_jobcard",
    "workshop_jobcardline",
    "projects_project",
    "projects_projectmilestone",
    "support_vendorticketshare",
    "insurance_policyproduct",
    "insurance_policyoptionset",
    "insurance_policyoption",
    "insurance_policy",
    "insurance_policyendorsement",
    "insurance_commissionreceivable",
    "insurance_policyclaim",
    "insurance_policykyc",
    "billing_tenantactivation",
    "billing_vendortenantsnapshot",
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
        ("core", "0037_rls_gst_period_filing"),
        ("workshop", "0001_roadmap_items"),
        ("projects", "0001_roadmap_items"),
        ("support", "0002_roadmap_items"),
        ("insurance", "0001_roadmap_items"),
        ("billing", "0010_roadmap_items"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
