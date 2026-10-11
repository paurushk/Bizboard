from django.db import migrations, models
import django.db.models.deletion


def backfill_void_reason(apps, schema_editor):
    """Lift "VOIDED[: reason]" lines already appended to notes into the new field."""
    from core.rls import rls_bypass

    with rls_bypass():
        Receipt = apps.get_model("payments", "CustomerReceipt")
        for row in Receipt.objects.filter(status="VOIDED", void_reason="").only("id", "notes", "updated_at"):
            reason = ""
            for line in reversed((row.notes or "").splitlines()):
                if line.startswith("VOIDED"):
                    reason = line[len("VOIDED"):].lstrip(": ").strip()
                    break
            Receipt.objects.filter(pk=row.pk).update(
                void_reason=reason[:500], voided_at=row.updated_at,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_initial"),
        ("payments", "0037_receipt_tendered_change"),
    ]

    operations = [
        migrations.AddField(
            model_name="customerreceipt",
            name="void_reason",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.AddField(
            model_name="customerreceipt",
            name="voided_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="customerreceipt",
            name="voided_by",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="+", to="accounts.user",
            ),
        ),
        migrations.AddIndex(
            model_name="customerreceipt",
            index=models.Index(fields=["company", "mode", "receipt_date"], name="receipt_co_mode_date_idx"),
        ),
        migrations.RunPython(backfill_void_reason, migrations.RunPython.noop),
    ]
