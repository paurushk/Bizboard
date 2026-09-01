from django.db import migrations, models


def _keep_one_primary(apps, schema_editor):
    CompanyGstin = apps.get_model("accounts", "CompanyGstin")
    seen = set()
    for row in CompanyGstin.objects.filter(is_primary=True).order_by("id"):
        if row.company_id in seen:
            row.is_primary = False
            row.save(update_fields=["is_primary"])
        else:
            seen.add(row.company_id)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0040_w0_07_outstanding_and_push"),
    ]

    operations = [
        migrations.RunPython(_keep_one_primary, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="companygstin",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_primary", True)),
                fields=("company",),
                name="uniq_company_one_primary_gstin",
            ),
        ),
    ]
