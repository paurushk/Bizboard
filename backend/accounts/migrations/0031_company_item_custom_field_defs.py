from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0030_fix_demo_gstin_checksum"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="item_custom_field_defs",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
