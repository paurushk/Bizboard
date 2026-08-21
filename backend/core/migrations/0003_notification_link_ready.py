# BB-000282: WhatsApp share-link status is LINK_READY, not SENT.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_fileasset_pdf_kinds"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="status",
            field=models.CharField(
                choices=[
                    ("QUEUED", "Queued"),
                    ("SENT", "Sent"),
                    ("LINK_READY", "Link Ready"),
                    ("FAILED", "Failed"),
                ],
                default="QUEUED",
                max_length=16,
            ),
        ),
    ]
