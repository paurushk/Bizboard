"""BILL-02 / HSN-01: seed the curated HSN → GST-rate starter table.

Previously only HSN 1905 and 2402 had rows, so `rate_for()` (which *overrides*
an invoice line's rate on the document date) was inert for every other item and
the GST 2.0 (22-Sep-2025) rate changes reached nothing. This seeds ~110 4-digit
chapter headings from `masters.hsn_catalog.STARTER_HSN_RATES`.

Idempotent (get_or_create on hsn_sac+version). Safe to re-run; re-runs pick up
new rows added to the spec. NOT a substitute for the full CBIC schedule — a CA
must verify before filing (see the disclaimer in hsn_catalog.py).
"""

from datetime import date

from django.db import migrations


def _parse(d):
    return date.fromisoformat(d) if d else None


def seed(apps, schema_editor):
    HsnRate = apps.get_model("masters", "HsnRate")
    from masters.hsn_catalog import STARTER_HSN_RATES

    for row in STARTER_HSN_RATES:
        HsnRate.objects.get_or_create(
            hsn_sac=row["hsn_sac"],
            version=row["version"],
            defaults={
                "rate": row["rate"],
                "cess": row["cess"],
                "valid_from": _parse(row["valid_from"]),
                "valid_to": _parse(row["valid_to"]),
                "source_ref": row.get("source_ref", "starter-table"),
            },
        )


def unseed(apps, schema_editor):
    HsnRate = apps.get_model("masters", "HsnRate")
    HsnRate.objects.filter(source_ref="starter-table").exclude(
        hsn_sac__in=["1905", "2402"]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("masters", "0013_c04_qty_slabs"),
        ("masters", "0010_b06_hsn_rate"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
