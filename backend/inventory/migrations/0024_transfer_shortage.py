from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0023_planwave_remaining"),
    ]

    operations = [
        migrations.AddField(
            model_name="stocktransferline",
            name="shortage_qty",
            field=models.DecimalField(decimal_places=3, default=Decimal("0"), max_digits=12),
        ),
        migrations.AddField(
            model_name="stocktransferline",
            name="shortage_reason",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
