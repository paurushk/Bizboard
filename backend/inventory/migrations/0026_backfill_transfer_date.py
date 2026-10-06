from django.db import migrations
from django.db.models.functions import TruncDate


def backfill_transfer_date(apps, schema_editor):
    """0021 added transfer_date with the migration day as the default for every existing row.

    The closed-period gate on cancel and receive reads this date, so a transfer made last year
    would have looked like it happened today. Rows whose date is later than the day they were
    created are exactly the ones that were stamped by the migration: reset them to their own day.
    """
    Transfer = apps.get_model("inventory", "StockTransfer")
    batch = []
    for row in Transfer.objects.annotate(created_day=TruncDate("created_at")).filter(
        transfer_date__gt=TruncDate("created_at"),
    ).iterator():
        row.transfer_date = row.created_day
        batch.append(row)
        if len(batch) >= 500:
            Transfer.objects.bulk_update(batch, ["transfer_date"])
            batch = []
    if batch:
        Transfer.objects.bulk_update(batch, ["transfer_date"])


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0025_stockbalance_product_protect"),
    ]

    operations = [
        migrations.RunPython(backfill_transfer_date, migrations.RunPython.noop),
    ]
