from django.db import migrations, models


def dedupe_open_quarantine(apps, schema_editor):
    """Keep the newest open row per company; close the rest so the constraint can apply."""
    from django.utils import timezone

    Row = apps.get_model("planwave", "IntegrityQuarantine")
    seen = set()
    for row in Row.objects.filter(cleared_at__isnull=True).order_by("-id"):
        if row.company_id in seen:
            row.cleared_at = timezone.now()
            row.save(update_fields=["cleared_at"])
        seen.add(row.company_id)


class Migration(migrations.Migration):

    dependencies = [
        ("planwave", "0003_finish_links"),
    ]

    operations = [
        migrations.RunPython(dedupe_open_quarantine, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="integrityquarantine",
            constraint=models.UniqueConstraint(
                condition=models.Q(("cleared_at__isnull", True)),
                fields=("company",),
                name="uniq_open_quarantine_per_company",
            ),
        ),
    ]
