from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("purchases", "0019_company_gstin"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchasecreditnote",
            name="rcm_cess",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14),
        ),
        migrations.AddField(
            model_name="purchasedebitnote",
            name="rcm_cess",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14),
        ),
    ]
