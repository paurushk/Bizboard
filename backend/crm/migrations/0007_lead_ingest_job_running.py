from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0006_lead_ingest_job"),
    ]

    operations = [
        migrations.AlterField(
            model_name="leadingestjob",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending"),
                    ("RUNNING", "Running"),
                    ("DONE", "Done"),
                    ("FAILED", "Failed"),
                ],
                default="PENDING",
                max_length=16,
            ),
        ),
    ]
