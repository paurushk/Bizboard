from django.db import migrations

CHUNK = 500


def forwards(apps, schema_editor):
    WorkOrder = apps.get_model("manufacturing", "WorkOrder")
    qs = WorkOrder.objects.filter(status="RELEASED", released_at__isnull=True).order_by("pk")
    last_pk = 0
    while True:
        batch = list(qs.filter(pk__gt=last_pk)[:CHUNK])
        if not batch:
            break
        last_pk = batch[-1].pk
        for wo in batch:
            created = getattr(wo, "created_at", None)
            wo.released_at = created.date() if created is not None else None
            wo.save(update_fields=["released_at"])


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("manufacturing", "0009_bomline_bomline_qty_gt_0_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
