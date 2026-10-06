from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("masters", "0023_product_trgm_gin"),
    ]

    operations = [
        migrations.AddField(
            model_name="supplier",
            name="income_tax_specified_person",
            field=models.BooleanField(default=False),
        ),
    ]
