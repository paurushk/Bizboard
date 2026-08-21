from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("purchases", "0017_wave18_cess_itc"),
    ]

    operations = [
        migrations.AlterField(
            model_name="purchaseinvoice",
            name="itc_eligibility",
            field=models.CharField(
                choices=[
                    ("UNREVIEWED", "Unreviewed"),
                    ("CLAIMABLE", "Claimable"),
                    ("INELIGIBLE", "Ineligible"),
                    ("REVERSED", "Reversed"),
                ],
                default="UNREVIEWED",
                help_text="BB-000614: never claim ITC until explicitly marked CLAIMABLE.",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="purchaseinvoice",
            name="rcm_cess",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14),
        ),
    ]
