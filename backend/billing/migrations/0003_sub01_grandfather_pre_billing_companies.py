from datetime import timedelta

from django.db import migrations
from django.utils import timezone


GRANDFATHER_TRIAL_DAYS = 60


def forwards(apps, schema_editor):
    """SUB-01: every Company that predates SaaS billing (or whose
    ``ensure_register_trial`` never ran) has no Subscription row, so
    ``company_writes_blocked`` returns ``REQUIRE_SUBSCRIPTION`` and hard
    write-blocks them the moment this is deployed to a paid env.

    Give each such tenant a generous grandfathered TRIAL so they keep working;
    they convert to a paid plan through the normal billing flow before it lapses.
    """
    Company = apps.get_model("accounts", "Company")
    Subscription = apps.get_model("billing", "Subscription")
    Plan = apps.get_model("billing", "Plan")

    plan, _ = Plan.objects.get_or_create(
        slug="trial",
        defaults={
            "name": "Trial",
            "seat_limit": 3,
            "price_paise": 0,
            "is_active": True,
            "modules": {},
        },
    )

    have_sub = set(Subscription.objects.values_list("company_id", flat=True))
    trial_ends = timezone.now() + timedelta(days=GRANDFATHER_TRIAL_DAYS)
    rows = [
        Subscription(
            company_id=cid,
            plan_id=plan.id,
            status="trial",
            trial_ends_at=trial_ends,
        )
        for cid in Company.objects.exclude(id__in=have_sub).values_list("id", flat=True)
    ]
    if rows:
        Subscription.objects.bulk_create(rows, batch_size=500)


def backwards(apps, schema_editor):
    # Non-reversible in a meaningful way (we cannot tell a grandfathered trial
    # from a genuine one). No-op.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0002_rename_billing_sub_status_trial_idx_billing_sub_status_626969_idx_and_more"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
