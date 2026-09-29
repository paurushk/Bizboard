from django.db import migrations


def set_trial_modules(apps, schema_editor):
    from core.services.feature_flags import ROLLOUT_GRANTABLE_KEYS

    Plan = apps.get_model("billing", "Plan")
    modules = {key: True for key in sorted(ROLLOUT_GRANTABLE_KEYS)}
    Plan.objects.filter(slug="trial").update(modules=modules)


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0007_dead_letter_event_dedup_constraint"),
    ]

    operations = [
        migrations.RunPython(set_trial_modules, migrations.RunPython.noop),
    ]
