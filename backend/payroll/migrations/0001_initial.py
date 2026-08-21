# Generated manually for Wave 17D

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0021_wave16d_supply_gstin"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Employee",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=200)),
                ("code", models.CharField(max_length=32)),
                ("salary", models.DecimalField(decimal_places=2, max_digits=14)),
                ("status", models.CharField(
                    choices=[("ACTIVE", "Active"), ("INACTIVE", "Inactive")],
                    default="ACTIVE", max_length=16,
                )),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="accounts.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="PayRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("period", models.CharField(help_text="YYYY-MM", max_length=7)),
                ("status", models.CharField(
                    choices=[("DRAFT", "Draft"), ("COMPLETED", "Completed")],
                    default="DRAFT", max_length=16,
                )),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="accounts.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-period"]},
        ),
        migrations.CreateModel(
            name="PaySlip",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("gross", models.DecimalField(decimal_places=2, max_digits=14)),
                ("deductions", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("net", models.DecimalField(decimal_places=2, max_digits=14)),
                ("employee", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payslips", to="payroll.employee")),
                ("pay_run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="slips", to="payroll.payrun")),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.AddConstraint(
            model_name="employee",
            constraint=models.UniqueConstraint(fields=("company", "code"), name="uniq_employee_code_per_company"),
        ),
        migrations.AddConstraint(
            model_name="payrun",
            constraint=models.UniqueConstraint(fields=("company", "period"), name="uniq_payrun_period_per_company"),
        ),
        migrations.AddConstraint(
            model_name="payslip",
            constraint=models.UniqueConstraint(fields=("pay_run", "employee"), name="uniq_payslip_employee_per_run"),
        ),
    ]
