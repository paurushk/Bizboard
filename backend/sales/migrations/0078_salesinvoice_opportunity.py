import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0016_opportunity_lost_reason_reopen"),
        ("sales", "0077_recurring_paused_reason"),
    ]

    operations = [
        migrations.AddField(
            model_name="salesinvoice",
            name="opportunity",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="invoices",
                to="crm.opportunity",
            ),
        ),
    ]
