"""CR-053: opening-stock uniqueness without mutating reference_type on void.

Void posts a compensating import_void ADJUSTMENT and leaves the original
OPENING_STOCK row intact. Uniqueness is split: manual openings stay one-per
location; import openings are unique per (location, reference_id) so a later
import job can re-open after void.
"""

from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0017_alter_stockmovement_unit_cost"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="stockmovement",
            name="uniq_opening_stock_with_batch",
        ),
        migrations.RemoveConstraint(
            model_name="stockmovement",
            name="uniq_opening_stock_no_batch",
        ),
        migrations.AddConstraint(
            model_name="stockmovement",
            constraint=models.UniqueConstraint(
                fields=["company", "warehouse", "product", "batch"],
                condition=Q(movement_type="OPENING_STOCK")
                & ~Q(reference_type__in=["import", "import_voided"])
                & Q(batch__isnull=False),
                name="uniq_opening_stock_manual_with_batch",
            ),
        ),
        migrations.AddConstraint(
            model_name="stockmovement",
            constraint=models.UniqueConstraint(
                fields=["company", "warehouse", "product"],
                condition=Q(movement_type="OPENING_STOCK")
                & ~Q(reference_type__in=["import", "import_voided"])
                & Q(batch__isnull=True),
                name="uniq_opening_stock_manual_no_batch",
            ),
        ),
        migrations.AddConstraint(
            model_name="stockmovement",
            constraint=models.UniqueConstraint(
                fields=["company", "warehouse", "product", "batch", "reference_id"],
                condition=Q(movement_type="OPENING_STOCK")
                & Q(reference_type="import")
                & Q(batch__isnull=False),
                name="uniq_opening_stock_import_with_batch",
            ),
        ),
        migrations.AddConstraint(
            model_name="stockmovement",
            constraint=models.UniqueConstraint(
                fields=["company", "warehouse", "product", "reference_id"],
                condition=Q(movement_type="OPENING_STOCK")
                & Q(reference_type="import")
                & Q(batch__isnull=True),
                name="uniq_opening_stock_import_no_batch",
            ),
        ),
    ]
