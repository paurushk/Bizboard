"""Widen AuditEvent.action to 64 chars.

Audit actions are dotted namespaces now (e.g. "tenant.restore_sandbox", 22
chars). SQLite ignores varchar length so this only bit on Postgres, where the
tenant restore endpoint 500'd with DataError (test_bb_000668).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0016_help_staff_all_rls"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditevent",
            name="action",
            field=models.CharField(
                choices=[
                    ("CREATE", "Create"),
                    ("UPDATE", "Update"),
                    ("DELETE", "Delete"),
                    ("LOGIN", "Login"),
                    ("LOGOUT", "Logout"),
                    ("IMPORT", "Import"),
                ],
                max_length=64,
            ),
        ),
    ]
