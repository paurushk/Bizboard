from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0025_sprint_b_payroll_pt_slabs"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="billing_override_active",
            field=models.BooleanField(default=False),
        ),
    ]
