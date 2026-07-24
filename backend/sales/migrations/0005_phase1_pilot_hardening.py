# Generated manually for Phase 1 pilot hardening

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0004_invoice_pdf_flag_defaults"),
    ]

    operations = [
        migrations.AddField(
            model_name="salesinvoice",
            name="invoice_discount_mode",
            field=models.CharField(
                choices=[
                    ("AFTER_TAX", "Cash discount (after tax)"),
                    ("BEFORE_TAX", "Discount (reduces GST)"),
                ],
                default="AFTER_TAX",
                max_length=12,
            ),
        ),
    ]
