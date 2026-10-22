"""WP-F2: existing books-off companies with history start with shadow posting OFF.

New companies (and books-off companies with nothing recorded yet) post to the ledger from day
one (``post_ledger`` default True). A books-off company that already has invoices, bills or stock
has history the ledger never saw; switching posting on without a back-fill would leave its
ledger half-filled. ``python manage.py enable_shadow_books --company <id>`` turns it on per
company: dry run, back-fill, books check (docs/ops/LEDGER_REPAIR_RUNBOOK.md).
"""

from django.db import migrations


def forwards(apps, schema_editor):
    Company = apps.get_model("accounts", "Company")
    SalesInvoice = apps.get_model("sales", "SalesInvoice")
    PurchaseInvoice = apps.get_model("purchases", "PurchaseInvoice")
    StockMovement = apps.get_model("inventory", "StockMovement")
    with_history = (
        set(SalesInvoice.objects.values_list("company_id", flat=True).distinct())
        | set(PurchaseInvoice.objects.values_list("company_id", flat=True).distinct())
        | set(StockMovement.objects.values_list("company_id", flat=True).distinct())
    )
    Company.objects.filter(accounting_enabled=False, pk__in=with_history).update(post_ledger=False)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0067_company_post_ledger"),
        ("sales", "0079_salesinvoice_statutory_licences_snapshot"),
        ("purchases", "0037_pur_open_defects"),
        ("inventory", "0033_mfg_phase0"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
