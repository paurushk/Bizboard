from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0060_partial_order_and_source"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="salesinvoice",
            index=models.Index(
                fields=["company", "customer", "status", "invoice_date"],
                name="sales_inv_co_cust_stat_dt_idx",
            ),
        ),
    ]
