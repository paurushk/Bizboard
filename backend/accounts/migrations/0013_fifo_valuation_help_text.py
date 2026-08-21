# BB-000062: document FIFO partial / WAVG-supported honesty on Company.inventory_valuation_method

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0012_wave4_tenancy_rbac_constraints"),
    ]

    operations = [
        migrations.AlterField(
            model_name="company",
            name="inventory_valuation_method",
            field=models.CharField(
                choices=[("WAVG", "Weighted Average"), ("FIFO", "FIFO")],
                default="WAVG",
                help_text=(
                    "WAVG is the supported costing method for COGS/on-hand value. "
                    "FIFO is partial: report replay may use layers, but outbound COGS "
                    "still uses blended remaining unit cost — not full perpetual FIFO. "
                    "Prefer WAVG until a dedicated FIFO layer ledger ships."
                ),
                max_length=8,
            ),
        ),
    ]
