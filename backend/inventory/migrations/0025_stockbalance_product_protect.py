import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0024_transfer_shortage"),
        ("masters", "0029_party_bank_account_text"),
    ]

    operations = [
        migrations.AlterField(
            model_name="stockbalance",
            name="product",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="stock_balances",
                to="masters.product",
            ),
        ),
    ]
