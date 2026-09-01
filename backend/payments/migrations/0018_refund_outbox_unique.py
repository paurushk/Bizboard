from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0017_rename_pay_dunning_co_sent_idx_payments_du_company_266787_idx_and_more"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="gatewayrefundoutbox",
            constraint=models.UniqueConstraint(
                fields=("gateway_payment",),
                name="uniq_refund_outbox_per_gateway_payment",
            ),
        ),
    ]
