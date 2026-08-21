from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0028_partial_closures"),
    ]

    operations = [
        migrations.AddField(
            model_name="salesinvoice",
            name="ecommerce_operator_gstin",
            field=models.CharField(blank=True, max_length=15),
        ),
    ]
