from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("purchases", "0031_purchaseinvoice_bill_of_entry"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchasereturnitem",
            name="unit_name",
            field=models.CharField(blank=True, default="PCS", max_length=32),
        ),
    ]
