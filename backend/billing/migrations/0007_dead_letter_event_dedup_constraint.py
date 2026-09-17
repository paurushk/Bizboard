# Expand-only: partial unique constraint to close a check-then-create race in
# DLQ parking (recon._park / park_dead_letter) — two concurrent callers could
# both pass an exists() check and create duplicate PENDING rows for the same
# provider/event_id before either commits.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0006_subscription_saas_dunning"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="deadletterevent",
            constraint=models.UniqueConstraint(
                fields=["provider", "event_id"],
                condition=models.Q(status="pending"),
                name="billing_dlq_uniq_pending_provider_event",
            ),
        ),
    ]
