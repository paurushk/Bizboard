"""Wave 16A: optional Postgres RLS policies (enabled via POSTGRES_RLS_ENABLED + SET LOCAL).

SQLite/tests: no-op. Policies use current_setting('app.company_id') set by middleware.
"""

from django.db import migrations


ENABLE_SQL = r"""
DO $$
DECLARE
  tbl text;
BEGIN
  FOREACH tbl IN ARRAY ARRAY[
    'sales_salesinvoice',
    'purchases_purchaseinvoice',
    'payments_customerreceipt',
    'accounting_journalentry',
    'accounting_journalline',
    'masters_customer',
    'masters_supplier',
    'masters_product'
  ]
  LOOP
    BEGIN
      EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', tbl);
      EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', tbl);
      EXECUTE format(
        'DROP POLICY IF EXISTS bizboard_company_isolation ON %I',
        tbl
      );
      EXECUTE format(
        'CREATE POLICY bizboard_company_isolation ON %I
         USING (company_id::text = NULLIF(current_setting(''app.company_id'', true), ''''))
         WITH CHECK (company_id::text = NULLIF(current_setting(''app.company_id'', true), ''''))',
        tbl
      );
    EXCEPTION WHEN undefined_table THEN
      NULL;
    END;
  END LOOP;
END $$;
"""

DISABLE_SQL = r"""
DO $$
DECLARE
  tbl text;
BEGIN
  FOREACH tbl IN ARRAY ARRAY[
    'sales_salesinvoice',
    'purchases_purchaseinvoice',
    'payments_customerreceipt',
    'accounting_journalentry',
    'accounting_journalline',
    'masters_customer',
    'masters_supplier',
    'masters_product'
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
        ("core", "0004_wave16_gl_fifo_gstr2b"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
