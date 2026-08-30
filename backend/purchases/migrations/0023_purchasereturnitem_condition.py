from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("purchases", "0022_tax12_cess_amount"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchasereturnitem",
            name="condition",
            field=models.CharField(
                choices=[("SELLABLE", "Sellable"), ("DAMAGED", "Damaged")],
                default="SELLABLE",
                max_length=16,
            ),
        ),
    ]
