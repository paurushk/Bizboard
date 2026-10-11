"""B-tree prefix indexes for the UTR and reference search (PostgreSQL only; a no-op elsewhere).

Those two columns are searched "starts with" (``UPPER(col) LIKE 'ABC%'``). A trigram index can
serve that, but the planner often prefers to walk every receipt of the company when the term is
not obviously rare. A B-tree on ``(company_id, UPPER(col) text_pattern_ops)`` answers a prefix
search directly, for any length of term. Built CONCURRENTLY (non-atomic migration); an index left
invalid by an interrupted build is dropped and rebuilt, see payments.0039.
"""

from django.db import migrations

INDEXES = (
    ("receipt_utr_prefix_idx", "utr"),
    ("receipt_reference_prefix_idx", "reference"),
)

_INVALID_SQL = (
    "SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
    "WHERE c.relname = %s AND NOT i.indisvalid"
)


def create_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for name, column in INDEXES:
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(_INVALID_SQL, [name])
            broken = cursor.fetchone() is not None
        if broken:
            schema_editor.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
        schema_editor.execute(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} "
            f"ON payments_customerreceipt (company_id, (UPPER({column}::text)) text_pattern_ops)"
        )


def drop_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for name, _column in INDEXES:
        schema_editor.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("payments", "0042_receipt_summary_indexes"),
    ]

    operations = [
        migrations.RunPython(create_indexes, drop_indexes),
    ]
