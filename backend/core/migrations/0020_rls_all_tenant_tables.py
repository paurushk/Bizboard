"""SYS-01: Postgres Row-Level Security on every tenant (`company_id`) table.

Idempotent. No-op on SQLite / when POSTGRES_RLS_ENABLED is off at runtime — the
policies are inert until `PostgresRlsMiddleware` starts SETting `app.company_id`.

Policy per table:
    USING / WITH CHECK (
        company_id::text = NULLIF(current_setting('app.company_id', true), '')
        OR current_setting('app.rls_bypass', true) = '1'
    )

`app.rls_bypass = '1'` is the escape hatch for cross-tenant background work
(beat tasks that iterate every company) — see core.rls.rls_bypass(). Without a
company GUC and without the bypass GUC the policy matches no rows (fail closed).

`accounts_companyuser` / `accounts_companygstin` are intentionally excluded: the
middleware must read them to resolve the tenant *before* it can set the GUC.
"""

from django.db import migrations


# Every model with a `company` ForeignKey, minus the tenancy-resolution tables.
RLS_TABLES = [
    "accounting_account",
    "accounting_accountingperiod",
    "accounting_bankreconsession",
    "accounting_costcenter",
    "accounting_fixedasset",
    "accounting_journalentry",
    "accounting_journalline",
    "banking_aaconsent",
    "banking_aatransaction",
    "core_auditevent",
    "core_documentseries",
    "core_fileasset",
    "core_helpevent",
    "core_helpfeedback",
    "core_idempotencyrecord",
    "core_moneyfieldaudit",
    "core_notification",
    "core_statutorydocumentevent",
    "crm_lead",
    "crm_leadactivity",
    "crm_opportunity",
    "imports_importjob",
    "imports_supplierbilltemplate",
    "insights_aiusageledger",
    "insights_assistantthread",
    "insights_attentionrowstate",
    "insights_businessalertevent",
    "insights_businesshealthsnapshot",
    "insights_cashflowforecastrun",
    "insights_dailybusinesssummary",
    "insights_shopfloorevent",
    "integrations_integrationconnection",
    "integrations_integrationsyncrun",
    "inventory_batchlot",
    "inventory_expiryalertlog",
    "inventory_inventorycostlayer",
    "inventory_inventoryrunningcost",
    "inventory_inventoryvaluationsnapshot",
    "inventory_serialnumber",
    "inventory_stockbalance",
    "inventory_stockcountline",
    "inventory_stockcountsession",
    "inventory_stockmovement",
    "inventory_stocktransfer",
    "inventory_stocktransferline",
    "inventory_warehouse",
    "inventory_warehousereorderlevel",
    "manufacturing_bom",
    "manufacturing_bomline",
    "manufacturing_workorder",
    "manufacturing_workorderline",
    "masters_brand",
    "masters_category",
    "masters_customer",
    "masters_expensecategory",
    "masters_paymentmode",
    "masters_pricelist",
    "masters_pricelistitem",
    "masters_product",
    "masters_supplier",
    "masters_taxrate",
    "masters_unit",
    "payments_bankaccount",
    "payments_bankstatement",
    "payments_bankstatementline",
    "payments_customerreceipt",
    "payments_dunningreminder",
    "payments_gatewaypayment",
    "payments_gatewayrefundoutbox",
    "payments_paymentallocation",
    "payments_paymentlink",
    "payments_reconmatch",
    "payments_supplierpayment",
    "payroll_employee",
    "payroll_payrun",
    "payroll_payslip",
    "purchases_purchasecreditnote",
    "purchases_purchasecreditnoteitem",
    "purchases_purchasedebitnote",
    "purchases_purchasedebitnoteitem",
    "purchases_purchaseinvoice",
    "purchases_purchaseitem",
    "purchases_purchaseorder",
    "purchases_purchaseorderitem",
    "purchases_purchasereturn",
    "purchases_purchasereturnitem",
    "reporting_gstr2bingest",
    "reporting_gstreturnperiod",
    "reporting_gstreturnsnapshot",
    "reporting_imsactionhistory",
    "sales_deliverychallan",
    "sales_deliverychallanitem",
    "sales_quotation",
    "sales_quotationitem",
    "sales_recurringinvoicerun",
    "sales_recurringinvoiceschedule",
    "sales_salescreditnote",
    "sales_salescreditnoteitem",
    "sales_salesdebitnote",
    "sales_salesdebitnoteitem",
    "sales_salesinvoice",
    "sales_salesitem",
    "sales_salesorder",
    "sales_salesorderitem",
    "sales_salesreturn",
    "sales_salesreturnitem",
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
        ("core", "0019_alter_auditevent_action"),
        # Every referenced tenant table (and its company_id column) exists from
        # each app's initial migration — CompanyScopedModel has always carried
        # company_id — so __first__ is enough and avoids dependency cycles.
        ("accounting", "__first__"),
        ("accounts", "__first__"),
        ("banking", "__first__"),
        ("crm", "__first__"),
        ("imports", "__first__"),
        ("insights", "__first__"),
        ("integrations", "__first__"),
        ("inventory", "__first__"),
        ("manufacturing", "__first__"),
        ("masters", "__first__"),
        ("payments", "__first__"),
        ("payroll", "__first__"),
        ("purchases", "__first__"),
        ("reporting", "__first__"),
        ("sales", "__first__"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
