from decimal import Decimal

from django.db import migrations, models
from django.db.models import F


def backfill_tendered(apps, schema_editor):
    # Receipts before this field handed over exactly what was applied.
    from core.rls import rls_bypass

    # Receipts may sit behind row-level security; the backfill spans every company.
    with rls_bypass():
        apps.get_model("payments", "CustomerReceipt").objects.filter(tendered=0).update(tendered=F("amount"))


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0036_receipt_shift"),
    ]

    operations = [
        migrations.AddField(
            model_name="customerreceipt",
            name="tendered",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14),
        ),
        migrations.AddField(
            model_name="customerreceipt",
            name="change_given",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14),
        ),
        migrations.RunPython(backfill_tendered, migrations.RunPython.noop),
    ]
