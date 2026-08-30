import django.db.models.deletion
from django.db import migrations, models


def backfill(apps, schema_editor):
    StockTransferLine = apps.get_model("inventory", "StockTransferLine")
    for line in StockTransferLine.objects.select_related("transfer").iterator():
        if line.transfer_id and not getattr(line, "company_id", None):
            StockTransferLine.objects.filter(pk=line.pk).update(company_id=line.transfer.company_id)


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0010_stockcountline_company"),
    ]

    operations = [
        migrations.AddField(
            model_name="stocktransferline",
            name="company",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="accounts.company",
            ),
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="stocktransferline",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="accounts.company",
            ),
        ),
    ]
