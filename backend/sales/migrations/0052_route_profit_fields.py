from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0051_sales_purchase_ux_plan"),
    ]

    operations = [
        migrations.AddField(
            model_name="deliveryroute",
            name="realized_revenue",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name="deliveryroute",
            name="realized_cogs",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name="deliveryroute",
            name="realized_profit",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name="deliveryroute",
            name="invoiced_stop_count",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="deliveryroute",
            name="stop_count",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
