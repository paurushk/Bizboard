import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("purchases", "0010_purchaseinvoice_cost_center_and_more"), ("accounting", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="purchaseinvoice",
            name="cost_center",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="purchase_invoices", to="accounting.costcenter",
            ),
        ),
    ]
