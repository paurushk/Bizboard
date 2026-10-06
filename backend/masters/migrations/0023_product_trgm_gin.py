from django.contrib.postgres.indexes import GinIndex
from django.db import migrations, models


def _create_trgm(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    schema_editor.execute(
        "CREATE INDEX IF NOT EXISTS product_name_sku_barcode_trgm "
        "ON masters_product USING gin "
        "(name gin_trgm_ops, sku gin_trgm_ops, barcode gin_trgm_ops)"
    )


def _drop_trgm(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP INDEX IF EXISTS product_name_sku_barcode_trgm")


class Migration(migrations.Migration):

    dependencies = [
        ("masters", "0022_product_gst_supply_form"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddIndex(
                    model_name="product",
                    index=GinIndex(
                        fields=["name", "sku", "barcode"],
                        name="product_name_sku_barcode_trgm",
                        opclasses=["gin_trgm_ops", "gin_trgm_ops", "gin_trgm_ops"],
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(_create_trgm, _drop_trgm),
            ],
        ),
    ]
