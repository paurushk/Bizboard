from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0009_track_readiness"),
    ]

    operations = [
        migrations.AddField(
            model_name="opportunity",
            name="competitor",
            field=models.CharField(blank=True, max_length=120),
        ),
    ]
