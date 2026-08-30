from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("masters", "0008_item_godown_expiry"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="wholesale_price",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=12),
        ),
    ]
