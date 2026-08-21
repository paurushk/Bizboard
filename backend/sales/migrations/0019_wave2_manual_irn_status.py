# BB-000214: distinct MANUAL_IRN einvoice_status for client-attested IRNs.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0018_document_line_company"),
    ]

    operations = [
        migrations.AlterField(
            model_name="salesinvoice",
            name="einvoice_status",
            field=models.CharField(
                choices=[
                    ("NONE", "None"),
                    ("READY", "Ready"),
                    ("GENERATED", "Generated"),
                    ("MANUAL_IRN", "Manual Irn"),
                    ("FAILED", "Failed"),
                    ("CANCELLED", "Cancelled"),
                ],
                default="NONE",
                max_length=16,
            ),
        ),
    ]
