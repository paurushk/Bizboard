# Generated manually for Wave 13 BB-000425

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0018_wave_c_can_post_journals"),
    ]

    operations = [
        migrations.AlterField(
            model_name="company",
            name="ai_features_enabled",
            field=models.BooleanField(default=False),
        ),
    ]
