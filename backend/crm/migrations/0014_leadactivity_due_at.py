from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0013_referral_reward_rejection_reason"),
    ]

    operations = [
        migrations.AddField(
            model_name="leadactivity",
            name="due_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="leadactivity",
            name="reminded_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
