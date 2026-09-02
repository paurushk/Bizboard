from django.db import migrations, models


def dedupe_blank_gstr2b(apps, schema_editor):
    Gstr2bIngest = apps.get_model("reporting", "Gstr2bIngest")
    seen = set()
    qs = Gstr2bIngest.objects.filter(invoice_number="", invoice_date__isnull=False).order_by("id")
    for row in qs.iterator():
        key = (row.company_id, row.period, row.supplier_gstin, row.invoice_date)
        if key in seen:
            row.delete()
        else:
            seen.add(key)
    seen_null = set()
    qs_null = Gstr2bIngest.objects.filter(invoice_number="", invoice_date__isnull=True).order_by("id")
    for row in qs_null.iterator():
        key = (row.company_id, row.period, row.supplier_gstin)
        if key in seen_null:
            row.delete()
        else:
            seen_null.add(key)


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0012_gstr2b_unique_doc"),
    ]

    operations = [
        migrations.RunPython(dedupe_blank_gstr2b, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="gstr2bingest",
            constraint=models.UniqueConstraint(
                condition=models.Q(("invoice_number", "")) & models.Q(("invoice_date__isnull", False)),
                fields=("company", "period", "supplier_gstin", "invoice_date"),
                name="uniq_gstr2b_ingest_blank_doc",
            ),
        ),
        migrations.AddConstraint(
            model_name="gstr2bingest",
            constraint=models.UniqueConstraint(
                condition=models.Q(("invoice_number", "")) & models.Q(("invoice_date__isnull", True)),
                fields=("company", "period", "supplier_gstin"),
                name="uniq_gstr2b_ingest_blank_null_date",
            ),
        ),
    ]
