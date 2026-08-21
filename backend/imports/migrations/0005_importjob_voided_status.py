from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("imports", "0004_bill_import_redesign"),
    ]

    operations = [
        migrations.AlterField(
            model_name="importjob",
            name="status",
            field=models.CharField(
                choices=[
                    ("UPLOADED", "Uploaded"),
                    ("EXTRACTING", "Extracting"),
                    ("NEEDS_CLARIFICATION", "Needs Clarification"),
                    ("PREVIEWED", "Previewed"),
                    ("COMMITTED", "Committed"),
                    ("FAILED", "Failed"),
                    ("VOIDED", "Voided"),
                ],
                default="UPLOADED",
                max_length=20,
            ),
        ),
    ]
