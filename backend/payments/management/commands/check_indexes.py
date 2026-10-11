"""Report PostgreSQL indexes left invalid by an interrupted ``CREATE INDEX CONCURRENTLY``.

An invalid index is kept up to date on every write but never used for reads, so it costs time and
helps with nothing, and a re-run of ``CREATE INDEX CONCURRENTLY IF NOT EXISTS`` silently skips it.
Exit status 1 when any is found, so a deploy runbook (or CI) can gate on it. With ``--fix`` each is
dropped concurrently so the owning migration (or ``migrate``) can rebuild it.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

SQL = (
    "SELECT n.nspname, c.relname, t.relname "
    "FROM pg_index i "
    "JOIN pg_class c ON c.oid = i.indexrelid "
    "JOIN pg_class t ON t.oid = i.indrelid "
    "JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE NOT i.indisvalid AND n.nspname NOT IN ('pg_catalog', 'information_schema') "
    "ORDER BY 1, 2"
)


class Command(BaseCommand):
    help = "List invalid PostgreSQL indexes (a failed concurrent build); --fix drops them."

    def add_arguments(self, parser):
        parser.add_argument("--fix", action="store_true", help="DROP INDEX CONCURRENTLY each invalid index.")

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            self.stdout.write("Not PostgreSQL: nothing to check.")
            return
        with connection.cursor() as cursor:
            cursor.execute(SQL)
            invalid = cursor.fetchall()
        if not invalid:
            self.stdout.write("All indexes are valid.")
            return
        for schema, index, table in invalid:
            self.stdout.write(f"INVALID: {schema}.{index} on {table}")
        if options["fix"]:
            # CONCURRENTLY cannot run inside a transaction block.
            connection.set_autocommit(True)
            with connection.cursor() as cursor:
                quote = connection.ops.quote_name
                for schema, index, _table in invalid:
                    # Identifiers come from the PostgreSQL catalog and are quoted; DDL takes no bind parameters.
                    statement = "DROP INDEX CONCURRENTLY IF EXISTS %s.%s" % (quote(schema), quote(index))
                    cursor.execute(statement)
                    self.stdout.write(f"dropped {schema}.{index}; run migrate to rebuild it")
            return
        raise CommandError(f"{len(invalid)} invalid index(es). Run with --fix, then migrate.")
