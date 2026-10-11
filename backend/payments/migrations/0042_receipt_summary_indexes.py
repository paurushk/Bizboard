"""Covering indexes behind the Money In totals (PostgreSQL only; a no-op elsewhere).

``summary/`` aggregates a company's receipts over a date range. The index carries every column the
aggregate reads (status, amount, mode, cheque status, TDS), so the planner answers it from the
index alone, with no heap fetches. It is deliberately NOT partial: the same query also counts the
voided and refunded rows (to report what was left out), and a ``WHERE status = 'POSTED'`` index
cannot serve that count.

The second index covers the live-allocation sum for the same receipts.

Built CONCURRENTLY (a non-atomic migration) so a large table is not locked against writes. An index
left invalid by an interrupted build is dropped and rebuilt, because ``IF NOT EXISTS`` would
otherwise skip it (see payments.0039).
"""

from django.db import migrations

INDEXES = (
    (
        "receipt_co_date_cover_idx",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS receipt_co_date_cover_idx "
        "ON payments_customerreceipt (company_id, receipt_date) "
        "INCLUDE (status, amount, mode, cheque_status, tds_deducted)",
    ),
    (
        "alloc_live_receipt_cover_idx",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS alloc_live_receipt_cover_idx "
        "ON payments_paymentallocation (receipt_id) INCLUDE (amount, tds_applied) "
        "WHERE reversed_at IS NULL AND receipt_id IS NOT NULL",
    ),
)

_INVALID_SQL = (
    "SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
    "WHERE c.relname = %s AND NOT i.indisvalid"
)


def create_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for name, create_sql in INDEXES:
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(_INVALID_SQL, [name])
            broken = cursor.fetchone() is not None
        if broken:
            schema_editor.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
        schema_editor.execute(create_sql)


def drop_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for name, _sql in INDEXES:
        schema_editor.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("payments", "0041_promise_auto_resolved"),
    ]

    operations = [
        migrations.RunPython(create_indexes, drop_indexes),
    ]
