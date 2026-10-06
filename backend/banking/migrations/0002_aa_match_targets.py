import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0012_account_monthly_balance"),
        ("banking", "0001_initial"),
        ("payments", "0035_cheque_dishonour_notice"),
    ]

    operations = [
        migrations.AddField(
            model_name="aatransaction",
            name="matched_supplier_payment",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="aa_transactions",
                to="payments.supplierpayment",
            ),
        ),
        migrations.AddField(
            model_name="aatransaction",
            name="matched_expense",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="aa_transactions",
                to="accounting.expense",
            ),
        ),
        migrations.AddConstraint(
            model_name="aatransaction",
            constraint=models.UniqueConstraint(
                condition=models.Q(matched_payment__isnull=False),
                fields=("matched_payment",),
                name="uniq_aa_txn_matched_receipt",
            ),
        ),
        migrations.AddConstraint(
            model_name="aatransaction",
            constraint=models.UniqueConstraint(
                condition=models.Q(matched_supplier_payment__isnull=False),
                fields=("matched_supplier_payment",),
                name="uniq_aa_txn_matched_supplier_payment",
            ),
        ),
        migrations.AddConstraint(
            model_name="aatransaction",
            constraint=models.UniqueConstraint(
                condition=models.Q(matched_expense__isnull=False),
                fields=("matched_expense",),
                name="uniq_aa_txn_matched_expense",
            ),
        ),
    ]
