import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0014_w0_06_running_cost"),
        ("sales", "0040_c04_applied_price_list_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="deliverychallanitem",
            name="batch",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="delivery_challan_items",
                to="inventory.batchlot",
            ),
        ),
        migrations.AddField(
            model_name="deliverychallanitem",
            name="batch_no",
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
