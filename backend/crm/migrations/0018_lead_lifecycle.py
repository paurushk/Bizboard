import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0017_referral_reward_basis_code_deactivation"),
    ]

    operations = [
        migrations.AddField(
            model_name="lead",
            name="lost_reason",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
        migrations.AddField(
            model_name="lead",
            name="lost_reason_note",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.AddField(
            model_name="lead",
            name="duplicate_of",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="duplicates",
                to="crm.lead",
            ),
        ),
        migrations.AddField(
            model_name="lead",
            name="dedupe_decision",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
    ]
