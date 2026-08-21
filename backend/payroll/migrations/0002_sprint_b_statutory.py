from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payroll", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="employee",
            name="esi_applicable",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="employee",
            name="pf_applicable",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="employee",
            name="pf_wage_ceiling",
            field=models.DecimalField(decimal_places=2, default=Decimal("15000.00"), max_digits=14),
        ),
        migrations.AddField(
            model_name="employee",
            name="pt_state",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="payslip",
            name="esi_employee",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="payslip",
            name="esi_employer",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="payslip",
            name="pf_employee",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="payslip",
            name="pf_employer",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="payslip",
            name="pt_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
    ]
