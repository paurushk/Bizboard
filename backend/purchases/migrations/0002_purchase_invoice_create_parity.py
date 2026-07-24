# Generated manually for purchase invoice create parity with sales.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
        ('purchases', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='purchaseinvoice',
            name='additional_charges',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name='purchaseinvoice',
            name='auto_round_off',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='purchaseinvoice',
            name='due_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='purchaseinvoice',
            name='include_bank_details',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='purchaseinvoice',
            name='include_payment_qr',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='purchaseinvoice',
            name='include_terms',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='purchaseinvoice',
            name='invoice_discount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name='purchaseinvoice',
            name='payment_terms_days',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='purchaseinvoice',
            name='signature',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='+',
                to='core.fileasset',
            ),
        ),
        migrations.AddField(
            model_name='purchaseinvoice',
            name='terms_text',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='purchaseitem',
            name='batch_no',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='purchaseitem',
            name='exp_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='purchaseitem',
            name='hsn_code',
            field=models.CharField(blank=True, max_length=8),
        ),
        migrations.AddField(
            model_name='purchaseitem',
            name='mfg_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='purchaseitem',
            name='mrp',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name='purchaseitem',
            name='unit_name',
            field=models.CharField(blank=True, default='PCS', max_length=32),
        ),
    ]
