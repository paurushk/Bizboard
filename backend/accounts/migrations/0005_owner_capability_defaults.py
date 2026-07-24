# Data migration: grant Phase 1 capability defaults to existing OWNER memberships

from django.db import migrations


def grant_owner_caps(apps, schema_editor):
    CompanyUser = apps.get_model("accounts", "CompanyUser")
    CompanyUser.objects.filter(role="OWNER").update(
        can_cancel_documents=True,
        can_view_financial_reports=True,
        can_export=True,
        can_manage_inventory=True,
        can_import=True,
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_phase1_pilot_hardening"),
    ]

    operations = [
        migrations.RunPython(grant_owner_caps, noop),
    ]
