import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0026_sprint_d_billing_override"),
        ("masters", "0001_initial"),
        ("sales", "0029_ecommerce_operator_gstin"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="salesinvoice",
            name="tcs_section",
            field=models.CharField(blank=True, max_length=16),
        ),
        migrations.AddField(
            model_name="salesinvoice",
            name="tcs_rate",
            field=models.DecimalField(decimal_places=3, default=0, max_digits=6),
        ),
        migrations.AddField(
            model_name="salesinvoice",
            name="tcs_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.CreateModel(
            name="RecurringInvoiceSchedule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("cadence", models.CharField(choices=[("MONTHLY", "Monthly"), ("WEEKLY", "Weekly")], default="MONTHLY", max_length=12)),
                ("next_run_at", models.DateTimeField()),
                ("is_active", models.BooleanField(default=True)),
                ("line_template", models.JSONField(blank=True, default=dict)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="recurring_invoice_schedules", to="accounts.company")),
                ("company_gstin", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="recurring_invoice_schedules", to="accounts.companygstin")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="recurring_invoice_schedules", to="masters.customer")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-next_run_at", "-id"]},
        ),
        migrations.CreateModel(
            name="RecurringInvoiceRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("period_key", models.CharField(max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="recurring_invoice_runs", to="accounts.company")),
                ("invoice", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="recurring_runs", to="sales.salesinvoice")),
                ("schedule", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="runs", to="sales.recurringinvoiceschedule")),
            ],
        ),
        migrations.AddIndex(
            model_name="recurringinvoiceschedule",
            index=models.Index(fields=["company", "is_active", "next_run_at"], name="sales_recur_company_idx"),
        ),
        migrations.AddIndex(
            model_name="recurringinvoicerun",
            index=models.Index(fields=["company", "period_key"], name="sales_recurrun_co_period_idx"),
        ),
        migrations.AddConstraint(
            model_name="recurringinvoicerun",
            constraint=models.UniqueConstraint(fields=("schedule", "period_key"), name="uniq_recurring_invoice_run_period"),
        ),
    ]
