from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0012_opportunity_open_stages"),
    ]

    operations = [
        migrations.AddField(
            model_name="referralreward",
            name="rejection_reason",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
    ]
