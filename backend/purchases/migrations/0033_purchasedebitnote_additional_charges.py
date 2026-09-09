from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("purchases", "0032_purchasereturnitem_unit_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchasedebitnote",
            name="additional_charges",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
    ]
