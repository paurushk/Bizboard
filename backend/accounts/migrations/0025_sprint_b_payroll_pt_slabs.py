from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0024_sprint3_fifo_gstin_series"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="payroll_pt_slabs",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
