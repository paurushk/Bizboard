from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0057_roadmap_items"),
        ("contracts", "0003_contract_products"),
    ]

    operations = [
        migrations.AddField(
            model_name="contract",
            name="recurring_schedule",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="contracts",
                to="sales.recurringinvoiceschedule",
            ),
        ),
    ]
