"""Wave 19E: expand Postgres RLS policies to all tenant business tables.

SQLite/tests: no-op. Runtime still requires POSTGRES_RLS_ENABLED + SET LOCAL.
Excludes login/tenancy bootstrap: accounts_company, accounts_companyuser, auth users.
"""

from django.db import migrations

TENANT_TABLES = [
    "accounting_account",
    "accounting_accountingperiod",
    "accounting_bankreconsession",
    "accounting_costcenter",
    "accounting_fixedasset",
    "accounting_journalentry",
    "accounting_journalline",
    "accounts_companygstin",
    "banking_aaconsent",
    "banking_aatransaction",
    "core_auditevent",
    "core_documentseries",
    "core_fileasset",
    "core_moneyfieldaudit",
    "core_notification",
    "core_statutorydocumentevent",
    "crm_lead",
    "crm_opportunity",
    "imports_importjob",
    "insights_aiusageledger",
    "insights_assistantthread",
    "insights_businessalertevent",
    "insights_businesshealthsnapshot",
    "insights_cashflowforecastrun",
    "insights_dailybusinesssummary",
    "integrations_integrationconnection",
    "integrations_integrationsyncrun",
    "inventory_batchlot",
    "inventory_inventorycostlayer",
    "inventory_serialnumber",
    "inventory_stockbalance",
    "inventory_stockmovement",
    "inventory_stocktransfer",
    "inventory_warehouse",
    "manufacturing_bom",
    "manufacturing_workorder",
    "masters_brand",
    "masters_category",
    "masters_customer",
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
    "payments_gatewaypayment",
    "payments_paymentallocation",
    "payments_paymentlink",
    "payments_reconmatch",
    "payments_supplierpayment",
    "payroll_employee",
    "payroll_payrun",
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
    "sales_deliverychallan",
    "sales_deliverychallanitem",
    "sales_quotation",
    "sales_quotationitem",
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


def _sql(enable: bool) -> str:
    tables_sql = ",\n    ".join(f"'{t}'" for t in TENANT_TABLES)
    if enable:
        body = """
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
"""
    else:
        body = """
      EXECUTE format('DROP POLICY IF EXISTS bizboard_company_isolation ON %I', tbl);
      EXECUTE format('ALTER TABLE %I DISABLE ROW LEVEL SECURITY', tbl);
"""
    return f"""
DO $$
DECLARE
  tbl text;
BEGIN
  FOREACH tbl IN ARRAY ARRAY[
    {tables_sql}
  ]
  LOOP
    BEGIN
      {body}
    EXCEPTION WHEN undefined_table THEN
      NULL;
    WHEN undefined_column THEN
      NULL;
    END;
  END LOOP;
END $$;
"""


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(_sql(True))


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(_sql(False))


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0007_wave18_statutory_irn_eway"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
