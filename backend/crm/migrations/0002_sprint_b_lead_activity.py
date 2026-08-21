import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0021_wave16d_supply_gstin"),
        ("crm", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LeadActivity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "kind",
                    models.CharField(
                        choices=[("NOTE", "Note"), ("CALL", "Call"), ("EMAIL", "Email")],
                        default="NOTE",
                        max_length=16,
                    ),
                ),
                ("body", models.TextField()),
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
                    "lead",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="activities",
                        to="crm.lead",
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
            options={"ordering": ["-created_at"], "verbose_name_plural": "lead activities"},
        ),
    ]
