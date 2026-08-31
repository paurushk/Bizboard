from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0015_a07_dunning_reminder"),
    ]

    operations = [
        migrations.AddField(
            model_name="gatewaypayment",
            name="holding_reason",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="gatewaypayment",
            name="holding_error",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="gatewaypayment",
            name="holding_since",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="gatewaypayment",
            name="internal_utr",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
        migrations.AlterField(
            model_name="gatewaypayment",
            name="status",
            field=models.CharField(
                choices=[
                    ("CREATED", "Created"),
                    ("CAPTURED", "Captured"),
                    ("CAPTURED_PENDING_BOOKS", "Captured Pending Books"),
                    ("FAILED", "Failed"),
                    ("REFUNDED", "Refunded"),
                ],
                default="CREATED",
                max_length=32,
            ),
        ),
        migrations.AddIndex(
            model_name="gatewaypayment",
            index=models.Index(fields=["company", "status"], name="pay_gp_company_status_idx"),
        ),
    ]
