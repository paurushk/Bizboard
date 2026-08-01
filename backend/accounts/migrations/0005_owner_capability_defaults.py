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


def revert_owner_caps(apps, schema_editor):
    """BUG-720: the previous reverse was a silent no-op — rolling back past
    this migration looked successful while leaving every owner's granted
    capability flags in place, which could surprise an operator debugging a
    permissions regression after a rollback."""
    CompanyUser = apps.get_model("accounts", "CompanyUser")
    CompanyUser.objects.filter(role="OWNER").update(
        can_cancel_documents=False,
        can_view_financial_reports=False,
        can_export=False,
        can_manage_inventory=False,
        can_import=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_phase1_pilot_hardening"),
    ]

    operations = [
        migrations.RunPython(grant_owner_caps, revert_owner_caps),
    ]
