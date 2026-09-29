from django.db import migrations, models


def strip_trial_filing_modules(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    plan = Plan.objects.filter(slug="trial").first()
    if plan is None or not isinstance(plan.modules, dict):
        return
    modules = dict(plan.modules)
    for key in ("ENABLE_GSTR", "ENABLE_TALLY", "ENABLE_GSTN_JSON"):
        modules.pop(key, None)
    plan.modules = modules
    plan.save(update_fields=["modules"])


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0010_roadmap_items"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscription",
            name="pending_razorpay_subscription_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.RunPython(strip_trial_filing_modules, migrations.RunPython.noop),
    ]
