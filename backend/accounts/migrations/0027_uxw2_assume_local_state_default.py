from django.db import migrations, models


def enable_assume_local_for_existing(apps, schema_editor):
    """UXW2-003/010: retail default — blank party state uses local CGST+SGST."""
    Company = apps.get_model("accounts", "Company")
    Company.objects.filter(assume_local_state_for_blank_party=False).update(
        assume_local_state_for_blank_party=True
    )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0026_sprint_d_billing_override"),
    ]

    operations = [
        migrations.AlterField(
            model_name="company",
            name="assume_local_state_for_blank_party",
            field=models.BooleanField(
                default=True,
                help_text="When party state/GSTIN is blank, treat as local (intra-state) for GST tax.",
            ),
        ),
        migrations.RunPython(enable_assume_local_for_existing, migrations.RunPython.noop),
    ]
