from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0011_sales_purchase_ux_plan"),
        ("accounts", "0054_sales_purchase_ux_plan"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="journalline",
            index=models.Index(fields=["company", "account", "entry"], name="jl_company_acct_entry_idx"),
        ),
        migrations.CreateModel(
            name="AccountMonthlyBalance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("period", models.DateField(help_text="First day of the month.")),
                ("debit", models.DecimalField(decimal_places=2, default=0, max_digits=16)),
                ("credit", models.DecimalField(decimal_places=2, default=0, max_digits=16)),
                ("account", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="monthly_balances", to="accounting.account")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="account_monthly_balances", to="accounts.company")),
            ],
        ),
        migrations.AddConstraint(
            model_name="accountmonthlybalance",
            constraint=models.UniqueConstraint(fields=("company", "account", "period"), name="uniq_account_month_balance"),
        ),
        migrations.AddIndex(
            model_name="accountmonthlybalance",
            index=models.Index(fields=["company", "period"], name="acct_month_bal_co_period_idx"),
        ),
        migrations.CreateModel(
            name="AccountBalanceRollup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("max_line_id", models.PositiveBigIntegerField(default=0)),
                ("refreshed_at", models.DateTimeField(auto_now=True)),
                ("company", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="account_balance_rollup", to="accounts.company")),
            ],
        ),
    ]
