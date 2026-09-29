from django.db import migrations


def narrow_trial_plan(apps, schema_editor):
    """Grandfather in-use modules, then store the post-H1 trial dict.

    H0 holds and the H1 GSTR worksheet grant land in this one migration.
    ``trial_plan_modules()`` is the final dict: GSTR True, every other hold
    explicit False. Do not write False and then True in a later file.
    """
    from billing.services import grandfather_trial_module_use, trial_plan_modules

    grandfather_trial_module_use()
    Plan = apps.get_model("billing", "Plan")
    Plan.objects.filter(slug="trial").update(modules=trial_plan_modules())


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0011_pending_razorpay_subscription"),
        ("workshop", "0001_roadmap_items"),
        ("projects", "0001_roadmap_items"),
        ("insurance", "0002_policy_renewal_lead"),
    ]

    operations = [
        migrations.RunPython(narrow_trial_plan, migrations.RunPython.noop),
    ]
