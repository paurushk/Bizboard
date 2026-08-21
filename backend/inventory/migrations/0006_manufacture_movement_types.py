from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0005_wave16_gl_fifo_gstr2b"),
    ]

    operations = [
        migrations.AlterField(
            model_name="stockmovement",
            name="movement_type",
            field=models.CharField(
                choices=[
                    ("OPENING_STOCK", "Opening Stock"),
                    ("PURCHASE", "Purchase"),
                    ("SALE", "Sale"),
                    ("PURCHASE_RETURN", "Purchase Return"),
                    ("SALES_RETURN", "Sales Return"),
                    ("ADJUSTMENT", "Adjustment"),
                    ("TRANSFER_OUT", "Transfer Out"),
                    ("TRANSFER_IN", "Transfer In"),
                    ("MANUFACTURE_ISSUE", "Manufacture Issue"),
                    ("MANUFACTURE_RECEIPT", "Manufacture Receipt"),
                ],
                max_length=24,
            ),
        ),
    ]
