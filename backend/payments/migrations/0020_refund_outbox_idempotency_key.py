from django.db import migrations, models


def backfill_idempotency_keys(apps, schema_editor):
    Outbox = apps.get_model("payments", "GatewayRefundOutbox")
    for row in Outbox.objects.all().iterator():
        if row.idempotency_key:
            continue
        amt = row.amount
        row.idempotency_key = f"bb-refund-{row.gateway_payment_id}-{amt}"
        row.save(update_fields=["idempotency_key"])


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0019_recon_match_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="gatewayrefundoutbox",
            name="idempotency_key",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
        migrations.RunPython(backfill_idempotency_keys, migrations.RunPython.noop),
    ]
