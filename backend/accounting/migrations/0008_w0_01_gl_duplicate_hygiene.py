from django.db import migrations
from django.db.models import Count


def reverse_duplicate_posted_journals(apps, schema_editor):
    """W0-01: keep lowest id POSTED row per unique key; reverse extras."""
    JournalEntry = apps.get_model("accounting", "JournalEntry")
    dup_keys = (
        JournalEntry.objects.filter(status="POSTED", source_id__isnull=False)
        .values("company_id", "source_type", "source_id", "purpose")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
    )
    for key in dup_keys:
        rows = list(
            JournalEntry.objects.filter(
                company_id=key["company_id"],
                source_type=key["source_type"],
                source_id=key["source_id"],
                purpose=key["purpose"],
                status="POSTED",
            ).order_by("id")
        )
        keep, extras = rows[0], rows[1:]
        for extra in extras:
            extra.status = "REVERSED"
            note = (extra.narration or "").strip()
            flag = f"[W0-01 duplicate of journal {keep.pk}]"
            extra.narration = f"{note}\n{flag}".strip() if note else flag
            extra.save(update_fields=["status", "narration", "updated_at"])

    still = (
        JournalEntry.objects.filter(status="POSTED", source_id__isnull=False)
        .values("company_id", "source_type", "source_id", "purpose")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
        .exists()
    )
    if still:
        raise RuntimeError(
            "W0-01: duplicate POSTED journals remain after hygiene. Restore from backup."
        )


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0007_wave16_gl_fifo_gstr2b"),
    ]

    operations = [
        migrations.RunPython(reverse_duplicate_posted_journals, noop_reverse),
    ]
