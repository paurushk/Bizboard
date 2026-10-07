from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0064_pos_refund_and_pins"),
    ]

    operations = [
        migrations.AddField(
            model_name="salesinvoice",
            name="pos_outage_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
    ]
