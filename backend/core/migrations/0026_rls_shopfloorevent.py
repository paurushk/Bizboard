"""Re-apply tenant RLS after every tenant table exists.

`0020` depends on each app's `__first__` migration, so tables created later
were skipped via `EXCEPTION WHEN undefined_table`. This catch-up runs the
same idempotent ENABLE/FORCE/POLICY SQL against the canonical `RLS_TABLES`
list, after each app's current leaf migration.
"""

import importlib

from django.db import migrations

_rls = importlib.import_module("core.migrations.0020_rls_all_tenant_tables")


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        # This catch-up (unlike 0027/0028) re-applies RLS to the FULL
        # canonical table list (40+ tables) in one migration transaction. A
        # lock_timeout bounds how long it will wait on any single table's
        # ACCESS EXCLUSIVE-class lock (e.g. a long-running query on that
        # table) — the migration fails fast and can be retried instead of
        # stalling the whole deploy window indefinitely.
        cursor.execute("SET LOCAL lock_timeout = '5s'")
        cursor.execute(_rls.ENABLE_SQL)


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout = '5s'")
        cursor.execute(_rls.DISABLE_SQL)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0025_rls_company_statutory_licence"),
        ("accounting", "0010_fixedasset_block_key_fixedasset_method_and_more"),
        ("accounts", "0050_companystatutorylicence"),
        ("banking", "0001_initial"),
        ("crm", "0004_opportunity_closed_at"),
        ("imports", "0009_alter_importjob_errors_alter_importjob_extra_sheets_and_more"),
        ("insights", "0006_alter_shopfloorevent_event"),
        ("integrations", "0001_phase7_tally"),
        ("inventory", "0018_cr053_opening_stock_void_append_only"),
        ("manufacturing", "0010_r028_backfill_released_at"),
        ("masters", "0018_product_regulated_category"),
        ("payments", "0028_payeememory"),
        ("payroll", "0009_employee_tax_regime_payslip_edli_charges_and_more"),
        ("purchases", "0034_goodsreceipt_goodsreceiptitem_and_more"),
        ("reporting", "0013_gstr2b_blank_unique"),
        ("sales", "0049_cft_quotation_converted_qty_amend_revision"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
