from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0012_account_monthly_balance"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="fixedasset",
            name="depreciation_catchup_months",
            field=models.CharField(blank=True, default="", max_length=800),
        ),
        migrations.CreateModel(
            name="CashShiftRegister",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("business_date", models.DateField()),
                ("opening_float", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("denominations", models.JSONField(blank=True, default=dict)),
                ("expected_cash", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("counted_cash", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("variance", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("status", models.CharField(choices=[("OPEN", "Open"), ("CLOSED", "Closed")], default="OPEN", max_length=12)),
                ("locked_at", models.DateTimeField(blank=True, null=True)),
                ("cashier", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cash_shifts", to=settings.AUTH_USER_MODEL)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="accounts.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-business_date", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="cashshiftregister",
            constraint=models.UniqueConstraint(fields=("company", "cashier", "business_date"), name="uniq_cash_shift_per_cashier_day"),
        ),
    ]
