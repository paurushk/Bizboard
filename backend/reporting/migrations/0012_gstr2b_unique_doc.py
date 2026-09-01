from django.db import migrations, models


def dedupe_gstr2b(apps, schema_editor):
    Gstr2bIngest = apps.get_model("reporting", "Gstr2bIngest")
    seen = set()
    for row in Gstr2bIngest.objects.exclude(invoice_number="").order_by("id").iterator():
        key = (row.company_id, row.period, row.supplier_gstin, row.invoice_number)
        if key in seen:
            row.delete()
        else:
            seen.add(key)


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0011_rename_reporting_g_company_ims_idx_reporting_g_company_3215ab_idx_and_more"),
    ]

    operations = [
        migrations.RunPython(dedupe_gstr2b, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="gstr2bingest",
            constraint=models.UniqueConstraint(
                condition=models.Q(("invoice_number", ""), _negated=True),
                fields=("company", "period", "supplier_gstin", "invoice_number"),
                name="uniq_gstr2b_ingest_doc",
            ),
        ),
    ]
