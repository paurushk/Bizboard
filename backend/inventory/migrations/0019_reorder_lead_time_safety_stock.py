from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0018_cr053_opening_stock_void_append_only"),
    ]

    operations = [
        migrations.AddField(
            model_name="warehousereorderlevel",
            name="lead_time_days",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="warehousereorderlevel",
            name="safety_stock_qty",
            field=models.DecimalField(decimal_places=3, default=Decimal("0"), max_digits=12),
        ),
    ]
