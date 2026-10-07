from datetime import datetime

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def backfill_shifts(apps, schema_editor):
    Shift = apps.get_model("accounting", "CashShiftRegister")
    opens = {}
    for row in Shift.objects.filter(status="OPEN").iterator():
        opens.setdefault((row.company_id, row.cashier_id), []).append(row.pk)
    dupes = {key: ids for key, ids in opens.items() if len(ids) > 1}
    if dupes:
        raise RuntimeError(
            "More than one open shift for a cashier. Close the extras "
            "(report_open_shifts) before migrating. " + str(dupes)
        )
    from zoneinfo import ZoneInfo

    kolkata = ZoneInfo("Asia/Kolkata")
    for row in Shift.objects.all().iterator():
        changed = []
        if not row.terminal_id:
            row.terminal_id = f"legacy-{row.cashier_id}"
            changed.append("terminal_id")
        if row.opened_at is None and row.business_date:
            row.opened_at = datetime.combine(row.business_date, datetime.min.time(), tzinfo=kolkata)
            changed.append("opened_at")
        if row.status == "CLOSED" and row.closed_at is None and row.locked_at is not None:
            row.closed_at = row.locked_at
            changed.append("closed_at")
        if changed:
            row.save(update_fields=changed)


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0014_cash_shift_cash_dropped"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="cashshiftregister",
            name="terminal_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="cashshiftregister",
            name="terminal_label",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="cashshiftregister",
            name="opened_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="cashshiftregister",
            name="closed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="CashDrop",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("note", models.CharField(blank=True, default="", max_length=200)),
                ("dropped_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="accounts.company")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("shift", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="drops", to="accounting.cashshiftregister")),
            ],
            options={"ordering": ["-dropped_at", "-id"]},
        ),
        migrations.RunPython(backfill_shifts, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="cashshiftregister",
            name="uniq_cash_shift_per_cashier_day",
        ),
        migrations.AddConstraint(
            model_name="cashshiftregister",
            constraint=models.UniqueConstraint(
                condition=models.Q(status="OPEN") & ~models.Q(terminal_id=""),
                fields=("company", "terminal_id"),
                name="uniq_open_cash_shift_per_terminal",
            ),
        ),
    ]
