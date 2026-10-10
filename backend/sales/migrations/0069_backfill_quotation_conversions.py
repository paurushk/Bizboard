"""Backfill the quotation conversion ledger from converted_quantity and the
legacy single converted_invoice / converted_order links.

Reverse is a no-op: reversing 0068 drops the table, and the backfill never
modifies converted_quantity or the legacy links.
"""

import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def forwards(apps, schema_editor):
    from sales.quotation_conversions import backfill_conversions

    counts = backfill_conversions(
        apps.get_model("sales", "QuotationItem"),
        apps.get_model("sales", "QuotationConversion"),
    )
    for company_id, unknown in sorted(counts.items()):
        if unknown:
            logger.warning(
                "quotation conversion backfill: company %s has %s UNKNOWN rows", company_id, unknown
            )


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0068_quotation_conversion_lifecycle"),
    ]
    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
