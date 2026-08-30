from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payroll", "0002_sprint_b_statutory"),
    ]

    operations = [
        migrations.AddField(
            model_name="employee",
            name="tds_rate",
            field=models.DecimalField(decimal_places=3, default=0, max_digits=6),
        ),
        migrations.AddField(
            model_name="payslip",
            name="tds_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
    ]
