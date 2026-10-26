from django.db import migrations

PAID_SLUGS = ("free", "starter", "pro", "enterprise")


def grant_gst_worksheets(apps, schema_editor):
    """D-16 (2026-10-25): the seeded plans grant GSTR-1/3B worksheets, like the trial.

    Only ENABLE_GSTR is set; every other module key on the plan is left as it is.
    """
    Plan = apps.get_model("billing", "Plan")
    for plan in Plan.objects.filter(slug__in=PAID_SLUGS):
        modules = dict(plan.modules or {})
        if modules.get("ENABLE_GSTR") is True:
            continue
        modules["ENABLE_GSTR"] = True
        plan.modules = modules
        plan.save(update_fields=["modules"])


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0020_relax_protect_fks"),
    ]

    operations = [
        migrations.RunPython(grant_gst_worksheets, migrations.RunPython.noop),
    ]
