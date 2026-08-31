from django.db import migrations, models
from django.db.models import Count, Q


def fail_if_duplicate_openings(apps, schema_editor):
    StockMovement = apps.get_model("inventory", "StockMovement")
    qs = (
        StockMovement.objects.filter(movement_type="OPENING_STOCK")
        .exclude(reference_type="import_voided")
        .values("company_id", "warehouse_id", "product_id", "batch_id")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
    )
    if qs.exists():
        sample = list(qs[:5])
        raise RuntimeError(
            "W0-08c: duplicate OPENING_STOCK movements exist; resolve before unique constraint. "
            f"Sample: {sample}"
        )


def noop(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0012_serialnumber_import_job_ref"),
    ]

    operations = [
        migrations.RunPython(fail_if_duplicate_openings, noop),
        migrations.AddConstraint(
            model_name="stockmovement",
            constraint=models.UniqueConstraint(
                condition=Q(movement_type="OPENING_STOCK")
                & ~Q(reference_type="import_voided")
                & Q(batch__isnull=False),
                fields=("company", "warehouse", "product", "batch"),
                name="uniq_opening_stock_with_batch",
            ),
        ),
        migrations.AddConstraint(
            model_name="stockmovement",
            constraint=models.UniqueConstraint(
                condition=Q(movement_type="OPENING_STOCK")
                & ~Q(reference_type="import_voided")
                & Q(batch__isnull=True),
                fields=("company", "warehouse", "product"),
                name="uniq_opening_stock_no_batch",
            ),
        ),
    ]
