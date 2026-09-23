import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0005_lead_pipeline"),
        ("sales", "0052_route_profit_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="quotation",
            name="opportunity",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="quotations",
                to="crm.opportunity",
            ),
        ),
    ]
