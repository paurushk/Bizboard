from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("insights", "0006_alter_shopfloorevent_event"),
    ]

    operations = [
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
                ],
                db_index=True,
                max_length=40,
            ),
        ),
    ]
