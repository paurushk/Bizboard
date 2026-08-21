# BB-000064: one GstReturnSnapshot per (company, return_type, period)

from django.db import migrations, models
from django.db.models import Count


def dedupe_gst_return_snapshots(apps, schema_editor):
    GstReturnSnapshot = apps.get_model("reporting", "GstReturnSnapshot")
    dupes = (
        GstReturnSnapshot.objects.values("company_id", "return_type", "period")
        .annotate(c=Count("id"))
        .filter(c__gt=1)
    )
    for row in dupes:
        qs = GstReturnSnapshot.objects.filter(
            company_id=row["company_id"],
            return_type=row["return_type"],
            period=row["period"],
        ).order_by("-generated_at", "-id")
        keep_id = qs.values_list("id", flat=True).first()
        if keep_id is not None:
            qs.exclude(pk=keep_id).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0002_wave4_tenancy_rbac_constraints"),
    ]

    operations = [
        migrations.RunPython(dedupe_gst_return_snapshots, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="gstreturnsnapshot",
            name="uniq_gst_return_snapshot_content",
        ),
        migrations.AddConstraint(
            model_name="gstreturnsnapshot",
            constraint=models.UniqueConstraint(
                fields=("company", "return_type", "period"),
                name="uniq_gst_return_snapshot_period",
            ),
        ),
    ]
