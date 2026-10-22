"""Enroll the manufacturing, quality and job work tables in tenant RLS (MFG-X5).

These tables are created after `0020`, so this catch-up applies the same
idempotent ENABLE/FORCE/POLICY SQL after the migrations that create them.
"""

from django.db import migrations

RLS_TABLES = [
    "inventory_tracelink",
    "manufacturing_mfgsettings",
    "manufacturing_bomoutput",
    "manufacturing_bomadditionalcost",
    "manufacturing_workorderoutput",
    "manufacturing_workordervariance",
    "manufacturing_materialissue",
    "manufacturing_materialissueline",
    "manufacturing_materialreturn",
    "manufacturing_materialreturnline",
    "manufacturing_productionreceipt",
    "manufacturing_productionreceiptline",
    "manufacturing_mrprun",
    "manufacturing_mrpline",
    "manufacturing_workcentre",
    "manufacturing_routingoperation",
    "manufacturing_jobcard",
    "manufacturing_operator",
    "manufacturing_timelog",
    "manufacturing_downtimereason",
    "manufacturing_downtimeevent",
    "manufacturing_machine",
    "manufacturing_maintenanceplan",
    "manufacturing_maintenancelog",
    "manufacturing_standardcost",
    "quality_defectcode",
    "quality_inspectiontemplate",
    "quality_inspectionparameter",
    "quality_inspection",
    "quality_inspectionresult",
    "quality_nonconformance",
    "jobwork_jobworkorder",
    "jobwork_jobworkchallan",
    "jobwork_jobworkchallanline",
    "jobwork_jobworkreceipt",
    "jobwork_jobworkreceiptline",
    "jobwork_jobworksettlement",
    "jobwork_principalmaterialmovement",
    "jobwork_itc04filing",
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
        ("core", "0063_documentseries_updated_at"),
        ("inventory", "0033_mfg_phase0"),
        ("manufacturing", "0014_bomadditionalcost_element_bomline_is_phantom_and_more"),
        ("quality", "0001_initial"),
        ("jobwork", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
