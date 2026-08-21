# Generated manually for TAX-12 specific (per-unit) cess.

from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0030_sprint_c_tcs_recurring"),
    ]

    operations = [
        migrations.AddField(
            model_name="deliverychallanitem",
            name="cess_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14),
        ),
        migrations.AddField(
            model_name="quotationitem",
            name="cess_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14),
        ),
        migrations.AddField(
            model_name="salescreditnoteitem",
            name="cess_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14),
        ),
        migrations.AddField(
            model_name="salesdebitnoteitem",
            name="cess_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14),
        ),
        migrations.AddField(
            model_name="salesitem",
            name="cess_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14),
        ),
        migrations.AddField(
            model_name="salesorderitem",
            name="cess_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14),
        ),
        migrations.AddField(
            model_name="salesreturnitem",
            name="cess_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14),
        ),
    ]
