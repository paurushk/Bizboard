# Generated manually for PURCHASE_BILL import + extraction fields

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("imports", "0001_initial"),
        ("masters", "0001_initial"),
        ("purchases", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="importjob",
            name="kind",
            field=models.CharField(
                choices=[
                    ("CUSTOMERS", "Customers"),
                    ("SUPPLIERS", "Suppliers"),
                    ("PRODUCTS", "Products"),
                    ("OPENING_STOCK", "Opening Stock"),
                    ("PURCHASE_BILL", "Purchase Bill"),
                ],
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="importjob",
            name="status",
            field=models.CharField(
                choices=[
                    ("UPLOADED", "Uploaded"),
                    ("EXTRACTING", "Extracting"),
                    ("PREVIEWED", "Previewed"),
                    ("COMMITTED", "Committed"),
                    ("FAILED", "Failed"),
                ],
                default="UPLOADED",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="importjob",
            name="supplier",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="masters.supplier",
            ),
        ),
        migrations.AddField(
            model_name="importjob",
            name="purchase_invoice",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="purchases.purchaseinvoice",
            ),
        ),
        migrations.AddField(
            model_name="importjob",
            name="failure_reason",
            field=models.TextField(blank=True),
        ),
    ]
