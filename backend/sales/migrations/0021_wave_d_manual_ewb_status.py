# BB-000273: MANUAL_EWB e-Way status for client-attested bills (not GSP-verified).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0020_wave10_opening_and_purchase_return_cn"),
    ]

    operations = [
        migrations.AlterField(
            model_name="salesinvoice",
            name="eway_status",
            field=models.CharField(
                choices=[
                    ("NONE", "None"),
                    ("READY", "Ready"),
                    ("GENERATED", "Generated"),
                    ("MANUAL_EWB", "Manual Ewb"),
                    ("FAILED", "Failed"),
                    ("CANCELLED", "Cancelled"),
                ],
                default="NONE",
                max_length=12,
            ),
        ),
        migrations.AlterField(
            model_name="deliverychallan",
            name="eway_status",
            field=models.CharField(
                choices=[
                    ("NONE", "None"),
                    ("READY", "Ready"),
                    ("GENERATED", "Generated"),
                    ("MANUAL_EWB", "Manual Ewb"),
                    ("FAILED", "Failed"),
                    ("CANCELLED", "Cancelled"),
                ],
                default="NONE",
                max_length=12,
            ),
        ),
    ]
