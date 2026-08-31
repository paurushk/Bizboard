from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0036_company_doc_number_scope"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="dunning_channel_sms",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="company",
            name="dunning_channel_whatsapp",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="company",
            name="dunning_days",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="company",
            name="dunning_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="company",
            name="dunning_max_reminders",
            field=models.PositiveSmallIntegerField(default=3),
        ),
        migrations.AddField(
            model_name="company",
            name="dunning_quiet_hours_end",
            field=models.PositiveSmallIntegerField(default=8),
        ),
        migrations.AddField(
            model_name="company",
            name="dunning_quiet_hours_start",
            field=models.PositiveSmallIntegerField(default=21),
        ),
    ]
