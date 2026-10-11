"""Trigram indexes behind the Money In search box (PostgreSQL only; a no-op elsewhere).

The list search matches receipt number (contains), UTR and reference (starts with), and the
customer's name and phone (contains). Django emits ``UPPER(col::text) LIKE UPPER(...)`` for
these, so each index is on that exact expression. Measured on 405,000 receipts across three
tenants: search went from 1.2-1.4 s to 16-70 ms (see MONEY_IN_IMPLEMENTATION_PLAN.md).

Built CONCURRENTLY so a large receipts table is not locked against writes; that needs a
non-atomic migration.

``CREATE INDEX CONCURRENTLY IF NOT EXISTS`` is NOT enough to survive an interrupted build:
PostgreSQL leaves the half-built index behind marked ``indisvalid = false`` under the same
name, so a re-run would see the name, skip the build and report success while the index is
unusable. Each index is therefore checked first and an invalid one is dropped and rebuilt.

``CREATE EXTENSION pg_trgm`` needs a privileged role on managed PostgreSQL (RDS, Cloud SQL).
Where the migrate role cannot create it, a DBA runs ``CREATE EXTENSION pg_trgm`` once and the
``IF NOT EXISTS`` here becomes a no-op.
"""

from django.db import migrations

INDEXES = (
    ("receipt_number_upper_trgm", "payments_customerreceipt", "number"),
    ("receipt_utr_upper_trgm", "payments_customerreceipt", "utr"),
    ("receipt_reference_upper_trgm", "payments_customerreceipt", "reference"),
    ("customer_name_upper_trgm", "masters_customer", "name"),
    ("customer_phone_upper_trgm", "masters_customer", "phone"),
)

_INVALID_SQL = (
    "SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
    "WHERE c.relname = %s AND NOT i.indisvalid"
)


def _drop_if_invalid(schema_editor, name):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(_INVALID_SQL, [name])
        broken = cursor.fetchone() is not None
    if broken:
        schema_editor.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")


def create_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for name, table, column in INDEXES:
        _drop_if_invalid(schema_editor, name)
        schema_editor.execute(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} "
            f"ON {table} USING gin (UPPER({column}::text) gin_trgm_ops)"
        )


def drop_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for name, _table, _column in INDEXES:
        schema_editor.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("masters", "0031_customer_is_pos_walk_in"),
        ("payments", "0038_receipt_void_audit"),
    ]

    operations = [
        migrations.RunPython(create_indexes, drop_indexes),
    ]
