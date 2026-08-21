from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0008_wave16_gl_fifo_gstr2b"),
    ]

    operations = [
        migrations.AddField(
            model_name="supplierpayment",
            name="status",
            field=models.CharField(
                choices=[("POSTED", "Posted"), ("VOIDED", "Voided")],
                db_index=True,
                default="POSTED",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="paymentallocation",
            name="reversed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="customerreceipt",
            constraint=models.UniqueConstraint(
                condition=~models.Q(utr=""),
                fields=("company", "utr"),
                name="uniq_receipt_utr_per_company",
            ),
        ),
        migrations.AddConstraint(
            model_name="supplierpayment",
            constraint=models.UniqueConstraint(
                condition=~models.Q(utr=""),
                fields=("company", "utr"),
                name="uniq_supplier_payment_utr_per_company",
            ),
        ),
    ]
