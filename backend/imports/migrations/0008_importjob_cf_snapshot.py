from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("imports", "0007_item_godown_expiry"),
    ]

    operations = [
        migrations.AddField(
            model_name="importjob",
            name="custom_field_defs_snapshot",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="importjob",
            name="custom_field_header_map",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
