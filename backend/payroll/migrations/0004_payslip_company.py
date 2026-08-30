import django.db.models.deletion
from django.db import migrations, models


def backfill_payslip_company(apps, schema_editor):
    PaySlip = apps.get_model("payroll", "PaySlip")
    for slip in PaySlip.objects.select_related("pay_run").iterator():
        if slip.pay_run_id and not slip.company_id:
            PaySlip.objects.filter(pk=slip.pk).update(company_id=slip.pay_run.company_id)


class Migration(migrations.Migration):

    dependencies = [
        ("payroll", "0003_employee_tds"),
    ]

    operations = [
        migrations.AddField(
            model_name="payslip",
            name="company",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="+",
                to="accounts.company",
            ),
        ),
        migrations.RunPython(backfill_payslip_company, migrations.RunPython.noop),
    ]
