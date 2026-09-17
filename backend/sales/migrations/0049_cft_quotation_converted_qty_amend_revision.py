from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0048_cr121_recurring_last_error"),
    ]

    operations = [
        migrations.AddField(
            model_name="quotationitem",
            name="converted_quantity",
            field=models.DecimalField(decimal_places=3, default=Decimal("0"), max_digits=12),
        ),
        migrations.AddField(
            model_name="salesinvoice",
            name="amend_revision",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
