import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0055_os_vision_plan"),
        ("sales", "0053_quotation_opportunity"),
    ]

    operations = [
        migrations.AddField(
            model_name="salesorder",
            name="credit_override_reason",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.AddField(
            model_name="salesorder",
            name="credit_overridden_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="accounts.companyuser",
            ),
        ),
        migrations.AddField(
            model_name="salesorder",
            name="credit_overridden_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="salesinvoice",
            name="credit_override_reason",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.AddField(
            model_name="salesinvoice",
            name="credit_overridden_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="accounts.companyuser",
            ),
        ),
        migrations.AddField(
            model_name="salesinvoice",
            name="credit_overridden_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
