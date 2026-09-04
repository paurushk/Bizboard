"""B8-025: retract the wrong post-cutover cess=0 starter rows.

Migration 0014 seeded a post-22-Sep-2025 row for every HSN in the starter
table, including 2202/2203/2402/2403/2404 (aerated drinks, beer, tobacco,
pan-masala) and 8703/8711 (motor cars, motorcycles) with cess hardcoded to
"0". GST 2.0 rationalised the *rate* to the 40% de-merit slab on these but did
NOT abolish compensation cess on them — the starter table has no
authoritative per-HSN post-cutover cess figure to put here (it varies by
engine size / per-unit specific cess), so rate_for() was silently telling
callers these HSNs carry zero cess post-cutover.

masters.hsn_catalog.STARTER_HSN_RATES no longer generates a post-cutover row
for these HSNs at all (falls through to the user/product-master cess entry
instead of asserting a wrong one). This migration deletes the stale
already-seeded rows from any database that ran 0014 before this fix — a
fresh database never has them (get_or_create in 0014 already skips them).
Only removes rows this repo seeded (source_ref="starter-table",
version=gst2.0-2025-09-22); never touches a rate a user or an admin edited
by hand into a different HsnRate row.
"""

from django.db import migrations

_HSNS = ("2202", "2203", "2402", "2403", "2404", "8703", "8711")
_POST_VERSION = "gst2.0-2025-09-22"


def remove_stale_rows(apps, schema_editor):
    HsnRate = apps.get_model("masters", "HsnRate")
    HsnRate.objects.filter(
        hsn_sac__in=_HSNS,
        version=_POST_VERSION,
        source_ref="starter-table",
    ).delete()


def restore_stale_rows(apps, schema_editor):
    # Best-effort reverse: re-seed the old (wrong) rows so `migrate` down is
    # not destructive of migration history — matches 0014's own unseed()
    # being a coarse best-effort, not a byte-exact restore.
    from datetime import date

    HsnRate = apps.get_model("masters", "HsnRate")
    from masters.hsn_catalog import _HSN_RATE_SPEC

    by_hsn = {spec[0]: spec for spec in _HSN_RATE_SPEC}
    for hsn in _HSNS:
        spec = by_hsn.get(hsn)
        if not spec:
            continue
        _hsn, _pre_r, _pre_c, post_r, post_c, _note = spec
        HsnRate.objects.get_or_create(
            hsn_sac=hsn,
            version=_POST_VERSION,
            defaults={
                "rate": post_r,
                "cess": post_c,
                "valid_from": date(2025, 9, 22),
                "valid_to": None,
                "source_ref": "starter-table",
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("masters", "0014_seed_hsn_rate_catalog"),
    ]

    operations = [
        migrations.RunPython(remove_stale_rows, restore_stale_rows),
    ]
