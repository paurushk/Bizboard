from django.db import migrations, models


def close_duplicate_open_counts(apps, schema_editor):
    """Keep the newest open count per godown; cancel the older ones (and say so in their notes)."""
    Session = apps.get_model("inventory", "StockCountSession")
    seen = set()
    for session in Session.objects.filter(status__in=["DRAFT", "COUNTED"]).order_by("-id"):
        key = (session.company_id, session.warehouse_id)
        if key not in seen:
            seen.add(key)
            continue
        note = "Cancelled automatically: another count was open for this godown."
        session.status = "CANCELLED"
        session.notes = f"{session.notes}\n{note}".strip()
        session.save(update_fields=["status", "notes"])


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0030_stockmovement_reason_code"),
    ]

    operations = [
        migrations.AddField(
            model_name="stockcountline",
            name="snapshot_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="stockcountline",
            name="counted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="stockcountline",
            name="filled_from_system",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="stockcountline",
            name="version",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(close_duplicate_open_counts, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="stockcountsession",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status__in", ["DRAFT", "COUNTED"])),
                fields=("company", "warehouse"),
                name="uniq_open_stock_count_per_godown",
            ),
        ),
    ]
