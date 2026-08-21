# Generated manually for Wave 14 P0 BB-000457

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0006_wave10_provider_link_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="customerreceipt",
            name="status",
            field=models.CharField(
                choices=[("POSTED", "Posted"), ("REFUNDED", "Refunded")],
                db_index=True,
                default="POSTED",
                max_length=16,
            ),
        ),
        migrations.AddIndex(
            model_name="customerreceipt",
            index=models.Index(fields=["company", "status"], name="payments_cu_company_status_idx"),
        ),
    ]
