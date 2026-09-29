from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("masters", "0020_customer_pincode"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="latitude",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name="customer",
            name="longitude",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
    ]
