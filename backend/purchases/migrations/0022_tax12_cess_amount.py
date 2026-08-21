# Generated manually for TAX-12 specific (per-unit) cess.

from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("purchases", "0021_sprint_c_tds"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchasecreditnoteitem",
            name="cess_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14),
        ),
        migrations.AddField(
            model_name="purchasedebitnoteitem",
            name="cess_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14),
        ),
        migrations.AddField(
            model_name="purchaseitem",
            name="cess_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14),
        ),
        migrations.AddField(
            model_name="purchaseorderitem",
            name="cess_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14),
        ),
        migrations.AddField(
            model_name="purchasereturnitem",
            name="cess_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14),
        ),
    ]
