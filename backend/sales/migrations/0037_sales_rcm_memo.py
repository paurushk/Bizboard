from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0036_alter_deliverychallanitem_quantity_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="salesinvoice",
            name="rcm_cess",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="salesinvoice",
            name="rcm_cgst",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="salesinvoice",
            name="rcm_igst",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="salesinvoice",
            name="rcm_sgst",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="salesinvoice",
            name="rcm_taxable",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
    ]
