from decimal import Decimal

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def backfill_movement_date(apps, schema_editor):
    StockMovement = apps.get_model("inventory", "StockMovement")
    from django.db.models.functions import TruncDate

    StockMovement.objects.update(movement_date=TruncDate("created_at"))


def noop(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0038_w0_06_valuation_date_order"),
        ("inventory", "0013_w0_08_opening_stock_unique"),
        ("masters", "0013_c04_qty_slabs"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="stockmovement",
            name="movement_date",
            field=models.DateField(db_index=True, default=django.utils.timezone.localdate),
        ),
        migrations.RunPython(backfill_movement_date, noop),
        migrations.AddIndex(
            model_name="stockmovement",
            index=models.Index(fields=["company", "product", "movement_date"], name="inv_move_co_prod_date_idx"),
        ),
        migrations.AddIndex(
            model_name="stockmovement",
            index=models.Index(
                fields=["company", "warehouse", "product", "movement_date"],
                name="inv_move_co_wh_prod_date_idx",
            ),
        ),
        migrations.CreateModel(
            name="InventoryRunningCost",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("qty", models.DecimalField(decimal_places=3, default=Decimal("0"), max_digits=14)),
                ("value", models.DecimalField(decimal_places=4, default=Decimal("0"), max_digits=16)),
                (
                    "batch",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="running_costs",
                        to="inventory.batchlot",
                    ),
                ),
                (
                    "company",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="accounts.company"),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="running_costs",
                        to="masters.product",
                    ),
                ),
                (
                    "warehouse",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="running_costs",
                        to="inventory.warehouse",
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
            model_name="inventoryrunningcost",
            constraint=models.UniqueConstraint(
                condition=models.Q(("batch__isnull", False)),
                fields=("company", "warehouse", "product", "batch"),
                name="uniq_running_cost_with_batch",
            ),
        ),
        migrations.AddConstraint(
            model_name="inventoryrunningcost",
            constraint=models.UniqueConstraint(
                condition=models.Q(("batch__isnull", True)),
                fields=("company", "warehouse", "product"),
                name="uniq_running_cost_no_batch",
            ),
        ),
        migrations.CreateModel(
            name="InventoryValuationSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("period", models.CharField(db_index=True, max_length=7)),
                ("qty", models.DecimalField(decimal_places=3, default=Decimal("0"), max_digits=14)),
                ("value", models.DecimalField(decimal_places=4, default=Decimal("0"), max_digits=16)),
                (
                    "batch",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="inventory.batchlot",
                    ),
                ),
                (
                    "company",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="accounts.company"),
                ),
                (
                    "product",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="masters.product"),
                ),
                (
                    "warehouse",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="inventory.warehouse"),
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
            model_name="inventoryvaluationsnapshot",
            constraint=models.UniqueConstraint(
                condition=models.Q(("batch__isnull", False)),
                fields=("company", "period", "warehouse", "product", "batch"),
                name="uniq_val_snapshot_with_batch",
            ),
        ),
        migrations.AddConstraint(
            model_name="inventoryvaluationsnapshot",
            constraint=models.UniqueConstraint(
                condition=models.Q(("batch__isnull", True)),
                fields=("company", "period", "warehouse", "product"),
                name="uniq_val_snapshot_no_batch",
            ),
        ),
    ]
