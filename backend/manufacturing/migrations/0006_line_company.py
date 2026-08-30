import django.db.models.deletion
from django.db import migrations, models


def backfill(apps, schema_editor):
    BomLine = apps.get_model("manufacturing", "BomLine")
    for line in BomLine.objects.select_related("bom").iterator():
        if line.bom_id and not line.company_id:
            BomLine.objects.filter(pk=line.pk).update(company_id=line.bom.company_id)
    WorkOrderLine = apps.get_model("manufacturing", "WorkOrderLine")
    for line in WorkOrderLine.objects.select_related("work_order").iterator():
        if line.work_order_id and not getattr(line, "company_id", None):
            WorkOrderLine.objects.filter(pk=line.pk).update(company_id=line.work_order.company_id)


class Migration(migrations.Migration):

    dependencies = [
        ("manufacturing", "0005_bomline_company"),
    ]

    operations = [
        migrations.AddField(
            model_name="workorderline",
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
            model_name="bomline",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="accounts.company",
            ),
        ),
        migrations.AlterField(
            model_name="workorderline",
            name="company",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="accounts.company",
            ),
        ),
    ]
