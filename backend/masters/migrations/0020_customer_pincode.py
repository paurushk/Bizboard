from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("masters", "0019_sales_purchase_ux_plan"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="pincode",
            field=models.CharField(blank=True, max_length=10),
        ),
    ]
