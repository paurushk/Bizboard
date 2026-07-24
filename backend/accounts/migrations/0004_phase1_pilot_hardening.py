# Generated manually for Phase 1 pilot hardening

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_invoice_create_parity"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="assume_local_state_for_blank_party",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="companyuser",
            name="can_cancel_documents",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="companyuser",
            name="can_export",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="companyuser",
            name="can_view_financial_reports",
            field=models.BooleanField(default=True),
        ),
    ]
