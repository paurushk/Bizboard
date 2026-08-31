from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("masters", "0012_a07_dunning_opt_out"),
    ]

    operations = [
        migrations.AddField(
            model_name="pricelistitem",
            name="discount_pct",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=5),
        ),
        migrations.AddField(
            model_name="pricelistitem",
            name="max_qty",
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name="pricelistitem",
            name="min_qty",
            field=models.DecimalField(decimal_places=3, default=Decimal("1"), max_digits=12),
        ),
        migrations.RemoveConstraint(
            model_name="pricelistitem",
            name="uniq_product_price_per_list",
        ),
        migrations.AddConstraint(
            model_name="pricelistitem",
            constraint=models.UniqueConstraint(
                fields=("price_list", "product", "min_qty"),
                name="uniq_product_slab_per_list",
            ),
        ),
        migrations.AlterModelOptions(
            name="pricelistitem",
            options={"ordering": ["product_id", "min_qty"]},
        ),
    ]
