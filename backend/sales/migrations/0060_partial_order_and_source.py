import django.db.models.deletion
from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0059_credit_note_peeled_allocations"),
    ]

    operations = [
        migrations.AddField(
            model_name="salesinvoice",
            name="source_order",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="split_invoices",
                to="sales.salesorder",
            ),
        ),
        migrations.AlterField(
            model_name="salesorder",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("CONFIRMED", "Confirmed"),
                    ("PARTIALLY_CONVERTED", "Partially Converted"),
                    ("CONVERTED", "Converted"),
                    ("CANCELLED", "Cancelled"),
                ],
                default="DRAFT",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="salesorderitem",
            name="shipped_quantity",
            field=models.DecimalField(decimal_places=3, default=Decimal("0"), max_digits=12),
        ),
        migrations.AddField(
            model_name="salesorderitem",
            name="invoiced_quantity",
            field=models.DecimalField(decimal_places=3, default=Decimal("0"), max_digits=12),
        ),
    ]
