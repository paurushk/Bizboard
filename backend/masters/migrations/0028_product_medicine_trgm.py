from django.contrib.postgres.indexes import GinIndex
from django.db import migrations


def _create_trgm(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    schema_editor.execute(
        "CREATE INDEX IF NOT EXISTS product_medicine_trgm "
        "ON masters_product USING gin "
        "(salt gin_trgm_ops, composition gin_trgm_ops, manufacturer gin_trgm_ops)"
    )


def _drop_trgm(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP INDEX IF EXISTS product_medicine_trgm")


class Migration(migrations.Migration):

    dependencies = [
        ("masters", "0027_supplier_gstin_cancelled_on"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddIndex(
                    model_name="product",
                    index=GinIndex(
                        fields=["salt", "composition", "manufacturer"],
                        name="product_medicine_trgm",
                        opclasses=["gin_trgm_ops", "gin_trgm_ops", "gin_trgm_ops"],
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(_create_trgm, _drop_trgm),
            ],
        ),
    ]
