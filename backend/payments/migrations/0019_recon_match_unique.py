from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0018_refund_outbox_unique"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="reconmatch",
            constraint=models.UniqueConstraint(
                fields=("receipt",),
                condition=models.Q(receipt__isnull=False),
                name="uniq_recon_match_receipt",
            ),
        ),
        migrations.AddConstraint(
            model_name="reconmatch",
            constraint=models.UniqueConstraint(
                fields=("supplier_payment",),
                condition=models.Q(supplier_payment__isnull=False),
                name="uniq_recon_match_supplier_payment",
            ),
        ),
    ]
