import django.db.models.deletion
from django.db import migrations, models


def backfill_stock_count_line_company(apps, schema_editor):
    StockCountLine = apps.get_model("inventory", "StockCountLine")
    for line in StockCountLine.objects.select_related("session").iterator():
        StockCountLine.objects.filter(pk=line.pk).update(company_id=line.session.company_id)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0030_fix_demo_gstin_checksum"),
        ("inventory", "0009_item_godown_expiry"),
    ]

    operations = [
        migrations.AddField(
            model_name="stockcountline",
            name="company",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="accounts.company",
            ),
        ),
        migrations.RunPython(backfill_stock_count_line_company, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="stockcountline",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="accounts.company",
                db_index=True,
            ),
        ),
    ]
