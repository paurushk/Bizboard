from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0038_b06_hsn_rate"),
    ]

    operations = [
        migrations.AddField(
            model_name="salesinvoice",
            name="whatsapp_message_id",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="salesinvoice",
            name="whatsapp_send_status",
            field=models.CharField(
                choices=[
                    ("NONE", "None"),
                    ("QUEUED", "Queued"),
                    ("SENT", "Sent"),
                    ("FALLBACK_LINK", "Fallback Link"),
                    ("FAILED", "Failed"),
                ],
                default="NONE",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="salesinvoice",
            name="whatsapp_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="salesinvoice",
            name="whatsapp_share_link",
            field=models.TextField(blank=True, default=""),
        ),
    ]
