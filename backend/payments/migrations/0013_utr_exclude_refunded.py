from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0012_sprint_c_tds"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="customerreceipt",
            name="uniq_receipt_utr_per_company",
        ),
        migrations.AddConstraint(
            model_name="customerreceipt",
            constraint=models.UniqueConstraint(
                condition=~models.Q(utr="") & ~models.Q(status__in=["VOIDED", "REFUNDED"]),
                fields=("company", "utr"),
                name="uniq_receipt_utr_per_company",
            ),
        ),
    ]
