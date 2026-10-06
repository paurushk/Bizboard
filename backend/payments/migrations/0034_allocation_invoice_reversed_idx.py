from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0033_paymentpromise_amount"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="paymentallocation",
            index=models.Index(fields=["sales_invoice", "reversed_at"], name="alloc_sales_inv_rev_idx"),
        ),
        migrations.AddIndex(
            model_name="paymentallocation",
            index=models.Index(fields=["purchase_invoice", "reversed_at"], name="alloc_purch_inv_rev_idx"),
        ),
    ]
