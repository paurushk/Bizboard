import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0061_money_in_policy_settings"),
        ("crm", "0016_opportunity_lost_reason_reopen"),
    ]

    operations = [
        migrations.AddField(
            model_name="referralcode",
            name="deactivated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="referralcode",
            name="deactivated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="accounts.companyuser",
            ),
        ),
        migrations.AddField(
            model_name="referralreward",
            name="basis",
            field=models.CharField(
                choices=[("FLAT", "Flat"), ("PERCENT", "Percent")], default="FLAT", max_length=8,
            ),
        ),
        migrations.AddField(
            model_name="referralreward",
            name="review_note",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
    ]
