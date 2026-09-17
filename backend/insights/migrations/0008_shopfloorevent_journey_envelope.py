from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("insights", "0007_shopfloorevent_funnel_events"),
    ]

    operations = [
        migrations.AddField(
            model_name="shopfloorevent",
            name="failure_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("validation", "Validation"),
                    ("help_code", "Help Code"),
                    ("timeout", "Timeout"),
                    ("5xx", "Http 5Xx"),
                    ("offline", "Offline"),
                    ("unknown", "Unknown"),
                ],
                default="",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="shopfloorevent",
            name="feature",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="shopfloorevent",
            name="journey",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="shopfloorevent",
            name="request_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="shopfloorevent",
            name="role",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
        migrations.AddField(
            model_name="shopfloorevent",
            name="session_id",
            field=models.CharField(blank=True, default="", max_length=36),
        ),
        migrations.AddField(
            model_name="shopfloorevent",
            name="success",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="shopfloorevent",
            name="event",
            field=models.CharField(
                choices=[
                    ("invoice_complete", "Invoice Complete"),
                    ("pos_line_added", "Pos Line Added"),
                    ("offline_enqueue", "Offline Enqueue"),
                    ("offline_flush_fail", "Offline Flush Fail"),
                    ("complete_duration_ms", "Complete Duration Ms"),
                    ("time_to_first_invoice_ms", "Time To First Invoice Ms"),
                    ("allocation_reconciled", "Allocation Reconciled"),
                    ("period_closed", "Period Closed"),
                    ("signup_completed", "Signup Completed"),
                    ("wizard_tax_confirmed", "Wizard Tax Confirmed"),
                    ("wizard_completed", "Wizard Completed"),
                    ("journey_started", "Journey Started"),
                    ("journey_failed", "Journey Failed"),
                    ("journey_completed", "Journey Completed"),
                ],
                db_index=True,
                max_length=40,
            ),
        ),
        migrations.AddIndex(
            model_name="shopfloorevent",
            index=models.Index(fields=["request_id"], name="insights_sfe_request_id_idx"),
        ),
        migrations.AddIndex(
            model_name="shopfloorevent",
            index=models.Index(
                fields=["company", "journey", "occurred_on"],
                name="insights_sfe_co_journey_on_idx",
            ),
        ),
    ]
