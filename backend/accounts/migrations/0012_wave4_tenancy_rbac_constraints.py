# BB-000018: can_create_sales|purchases|payments capability flags

from django.db import migrations, models


def grant_write_caps(apps, schema_editor):
    CompanyUser = apps.get_model("accounts", "CompanyUser")
    # Preserve current behavior for existing Owner and Staff memberships.
    CompanyUser.objects.all().update(
        can_create_sales=True,
        can_create_purchases=True,
        can_create_payments=True,
    )


def revert_write_caps(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0011_otp_hash"),
    ]

    operations = [
        migrations.AddField(
            model_name="companyuser",
            name="can_create_sales",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="companyuser",
            name="can_create_purchases",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="companyuser",
            name="can_create_payments",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(grant_write_caps, revert_write_caps),
    ]
