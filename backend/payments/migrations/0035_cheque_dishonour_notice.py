import django.db.models.deletion
from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0045_idempotencyrecord_request_hash"),
        ("payments", "0034_allocation_invoice_reversed_idx"),
    ]

    operations = [
        migrations.AddField(
            model_name="customerreceipt",
            name="dishonour_fee",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14),
        ),
        migrations.AddField(
            model_name="customerreceipt",
            name="section_138_notice",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="section_138_notices",
                to="core.fileasset",
            ),
        ),
    ]
