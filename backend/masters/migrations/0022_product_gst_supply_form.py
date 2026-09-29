from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("masters", "0021_customer_coordinates"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="gst_supply_form",
            field=models.CharField(blank=True, default="", max_length=24),
        ),
    ]
