import django.db.models.deletion
from django.db import migrations, models


def backfill_bomline_company(apps, schema_editor):
    BomLine = apps.get_model("manufacturing", "BomLine")
    for line in BomLine.objects.select_related("bom").iterator():
        if line.bom_id and not line.company_id:
            BomLine.objects.filter(pk=line.pk).update(company_id=line.bom.company_id)


class Migration(migrations.Migration):

    dependencies = [
        ("manufacturing", "0004_wave22_f2_wo_lot_serial"),
    ]

    operations = [
        migrations.AddField(
            model_name="bomline",
            name="company",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="accounts.company",
            ),
        ),
        migrations.RunPython(backfill_bomline_company, migrations.RunPython.noop),
    ]
