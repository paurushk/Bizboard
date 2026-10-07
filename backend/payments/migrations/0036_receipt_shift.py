from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0015_pos_shift_terminal"),
        ("payments", "0035_cheque_dishonour_notice"),
    ]

    operations = [
        migrations.AddField(
            model_name="customerreceipt",
            name="paid_from_till",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="customerreceipt",
            name="shift",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="receipts",
                to="accounting.cashshiftregister",
            ),
        ),
        migrations.AddField(
            model_name="supplierpayment",
            name="paid_from_till",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="supplierpayment",
            name="shift",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="supplier_payments",
                to="accounting.cashshiftregister",
            ),
        ),
    ]
