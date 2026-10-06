from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("masters", "0028_product_medicine_trgm"),
    ]

    operations = [
        migrations.AlterField(
            model_name="customer",
            name="party_bank_account",
            field=models.TextField(blank=True),
        ),
    ]
