# Generated manually for Wave 18G (BB-000177)

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0022_wave17_multi_company_feature_flags"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0005_wave16_postgres_rls"),
    ]

    operations = [
        migrations.CreateModel(
            name="StatutoryDocumentEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("entity_type", models.CharField(max_length=64)),
                ("entity_id", models.PositiveBigIntegerField()),
                (
                    "event_type",
                    models.CharField(
                        choices=[("COMPLETE", "Complete"), ("AMEND", "Amend"), ("CANCEL", "Cancel")],
                        max_length=16,
                    ),
                ),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="statutory_events",
                        to="accounts.company",
                    ),
                ),
                (
                    "user",
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
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["company", "entity_type", "entity_id"],
                        name="stat_evt_entity_idx",
                    ),
                ],
            },
        ),
    ]
