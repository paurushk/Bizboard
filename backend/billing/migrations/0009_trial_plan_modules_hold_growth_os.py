from django.db import migrations


def set_trial_modules(apps, schema_editor):
    """Re-apply the trial plan's module grant using the current, correct rule.

    0008_trial_plan_modules granted every ROLLOUT_GRANTABLE_KEYS entry,
    including the four Growth OS flags added to that set afterward
    (ENABLE_COMPLAINTS, ENABLE_SUPPORT_TICKETS, ENABLE_CONTRACTS,
    ENABLE_REFERRALS) — each of which is meant to stay out of the trial
    module list until it's stable in production, per
    billing.services.trial_plan_modules(). Since RunPython in 0008 imports
    ROLLOUT_GRANTABLE_KEYS live rather than a frozen snapshot, re-running
    migrate today (a fresh environment, a fresh CI database) would grant
    all four contrary to that decision. This migration doesn't edit 0008
    (already-applied migrations aren't edited) — it re-asserts the correct
    module set on top of it.
    """
    from billing.services import trial_plan_modules

    Plan = apps.get_model("billing", "Plan")
    Plan.objects.filter(slug="trial").update(modules=trial_plan_modules())


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0008_trial_plan_modules"),
    ]

    operations = [
        migrations.RunPython(set_trial_modules, migrations.RunPython.noop),
    ]
