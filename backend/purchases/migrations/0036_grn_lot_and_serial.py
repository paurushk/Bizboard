import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0021_transfer_transit_and_reservations"),
        ("purchases", "0035_sales_purchase_ux_plan"),
    ]

    operations = [
        migrations.AddField(
            model_name="goodsreceiptitem",
            name="batch",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="goods_receipt_items",
                to="inventory.batchlot",
            ),
        ),
        migrations.AddField(
            model_name="goodsreceiptitem",
            name="batch_no",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="goodsreceiptitem",
            name="mfg_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="goodsreceiptitem",
            name="exp_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="goodsreceiptitem",
            name="serial_numbers",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
