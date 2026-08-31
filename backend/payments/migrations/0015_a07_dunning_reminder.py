import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0037_a07_dunning"),
        ("masters", "0012_a07_dunning_opt_out"),
        ("payments", "0014_remaining_backlog_tcs_charges_outbox"),
        ("sales", "0039_a06_whatsapp_send_status"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DunningReminder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("sent_on", models.DateField()),
                ("days_overdue", models.PositiveIntegerField()),
                (
                    "channel",
                    models.CharField(choices=[("WHATSAPP", "Whatsapp"), ("SMS", "Sms")], max_length=16),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("SENT", "Sent"), ("SKIPPED", "Skipped"), ("FAILED", "Failed")],
                        default="SENT",
                        max_length=16,
                    ),
                ),
                ("error", models.CharField(blank=True, default="", max_length=500)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="accounts.company",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "customer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="dunning_reminders",
                        to="masters.customer",
                    ),
                ),
                (
                    "invoice",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="dunning_reminders",
                        to="sales.salesinvoice",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-sent_on", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="dunningreminder",
            index=models.Index(fields=["company", "sent_on"], name="pay_dunning_co_sent_idx"),
        ),
        migrations.AddConstraint(
            model_name="dunningreminder",
            constraint=models.UniqueConstraint(fields=("invoice", "sent_on"), name="uniq_dunning_invoice_per_day"),
        ),
    ]
