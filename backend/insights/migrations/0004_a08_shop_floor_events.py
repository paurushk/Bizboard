from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ("insights", "0003_attention_row_state"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0039_w0_02_recompute_tax_on_complete"),
    ]

    operations = [
        migrations.CreateModel(
            name="ShopFloorEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("event", models.CharField(db_index=True, max_length=40)),
                ("duration_ms", models.PositiveIntegerField(blank=True, null=True)),
                ("tap_count", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("occurred_on", models.DateField(db_index=True)),
                (
                    "company",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="accounts.company"),
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
        migrations.AddIndex(
            model_name="shopfloorevent",
            index=models.Index(fields=["company", "event", "occurred_on"], name="ins_shop_co_ev_on_idx"),
        ),
    ]
