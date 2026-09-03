from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0020_refund_outbox_idempotency_key"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="gatewayrefundoutbox",
            name="uniq_refund_outbox_per_gateway_payment",
        ),
        migrations.AddConstraint(
            model_name="gatewayrefundoutbox",
            constraint=models.UniqueConstraint(
                fields=["gateway_payment", "amount"],
                name="uniq_refund_outbox_per_payment_amount",
            ),
        ),
    ]
