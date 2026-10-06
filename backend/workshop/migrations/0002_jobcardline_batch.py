import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0021_transfer_transit_and_reservations"),
        ("workshop", "0001_roadmap_items"),
    ]

    operations = [
        migrations.AddField(
            model_name="jobcardline",
            name="batch",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="job_card_lines",
                to="inventory.batchlot",
            ),
        ),
        migrations.AddField(
            model_name="jobcardline",
            name="batch_no",
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
