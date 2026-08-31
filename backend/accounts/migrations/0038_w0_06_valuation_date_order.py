from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0037_a07_dunning"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="valuation_business_date_order",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "W0-06: order historical valuation by movement_date instead of insert time. "
                    "Default off for existing companies — turning this on can restate inventory/COGS. Take a backup."
                ),
            ),
        ),
    ]
