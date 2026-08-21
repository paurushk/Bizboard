from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0022_wave17_multi_company_feature_flags"),
        ("core", "0008_wave19_rls_all_tenant_tables"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="IdempotencyRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("scope", models.CharField(max_length=64)),
                ("key", models.CharField(max_length=128)),
                ("status_code", models.PositiveSmallIntegerField(default=200)),
                ("body", models.JSONField(blank=True, default=dict)),
                ("resource_id", models.CharField(blank=True, max_length=64)),
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
        ),
        migrations.AddConstraint(
            model_name="idempotencyrecord",
            constraint=models.UniqueConstraint(
                fields=("company", "scope", "key"),
                name="uniq_idempotency_company_scope_key",
            ),
        ),
    ]
