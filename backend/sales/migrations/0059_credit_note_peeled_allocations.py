from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0058_salesinvoice_pos_assumed_local"),
    ]

    operations = [
        migrations.AddField(
            model_name="salescreditnote",
            name="peeled_receipt_allocations",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
