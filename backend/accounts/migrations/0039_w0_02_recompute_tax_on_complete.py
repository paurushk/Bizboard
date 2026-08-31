from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0038_w0_06_valuation_date_order"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="recompute_tax_on_complete",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "W0-02: after Complete stamps the filing GSTIN, recompute tax for that GSTIN's state. "
                    "Default off for existing companies. If grand total changes by more than ₹0.01, Complete "
                    "requires confirm_gstin_total_change. Turning this on can change CGST/SGST vs IGST on Complete."
                ),
            ),
        ),
    ]
