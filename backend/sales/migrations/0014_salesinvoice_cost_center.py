import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("sales", "0013_salesinvoice_cost_center_salesitem_serial_numbers_and_more"), ("accounting", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="salesinvoice",
            name="cost_center",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="sales_invoices", to="accounting.costcenter",
            ),
        ),
    ]
