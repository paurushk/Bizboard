from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0024_sprint3_fifo_gstin_series"),
        ("sales", "0026_sprint3_fifo_gstin_series"),
    ]

    operations = [
        migrations.AddField(
            model_name="salescreditnote",
            name="additional_charges",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="salescreditnote",
            name="filing_party_gstin",
            field=models.CharField(blank=True, max_length=15),
        ),
        migrations.AddField(
            model_name="salescreditnote",
            name="filing_place_of_supply",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="salescreditnote",
            name="company_gstin",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="sales_credit_notes",
                to="accounts.companygstin",
            ),
        ),
        migrations.AddField(
            model_name="salesdebitnote",
            name="additional_charges",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="salesdebitnote",
            name="filing_party_gstin",
            field=models.CharField(blank=True, max_length=15),
        ),
        migrations.AddField(
            model_name="salesdebitnote",
            name="filing_place_of_supply",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="salesdebitnote",
            name="company_gstin",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="sales_debit_notes",
                to="accounts.companygstin",
            ),
        ),
    ]
