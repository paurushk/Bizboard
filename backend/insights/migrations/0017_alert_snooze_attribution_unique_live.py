from django.conf import settings
from django.db import migrations, models


def resolve_duplicate_live_alerts(apps, schema_editor):
    """Keep the newest live row per (company, code, subject); resolve the rest."""
    Alert = apps.get_model("insights", "BusinessAlertEvent")
    seen = set()
    for row in Alert.objects.filter(status__in=["OPEN", "SNOOZED"]).order_by("-created_at", "-id"):
        key = (row.company_id, row.code, row.subject_key)
        if key in seen:
            row.status = "RESOLVED"
            row.save(update_fields=["status"])
        else:
            seen.add(key)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("insights", "0016_attention_action_event"),
    ]

    operations = [
        migrations.AddField(
            model_name="businessalertevent",
            name="snoozed_by",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="businessalertevent",
            name="snoozed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(resolve_duplicate_live_alerts, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="businessalertevent",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status__in", ["OPEN", "SNOOZED"])),
                fields=("company", "code", "subject_key"),
                name="uniq_live_business_alert",
            ),
        ),
    ]
