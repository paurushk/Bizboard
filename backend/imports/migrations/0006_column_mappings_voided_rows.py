from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("imports", "0005_importjob_voided_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="importjob",
            name="column_mappings",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="importjob",
            name="voided_rows",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
