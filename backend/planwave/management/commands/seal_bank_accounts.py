"""Seal bank account numbers that were saved before sealing existed.

    python manage.py seal_bank_accounts [--dry-run]

The pre_save hook seals a number whenever its row is saved, so rows nobody has touched since
the rollout are still plaintext in the database, backups and exports. This saves each such row
once. It needs PLANWAVE_DATA_KEY. Safe to re-run: sealed values are skipped.
"""

from django.core.management.base import BaseCommand

from core.rls import rls_bypass


class Command(BaseCommand):
    help = "Seal existing plaintext bank account numbers on companies and customers."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        from accounts.models import Company
        from masters.models import Customer

        total = 0
        with rls_bypass():
            for model, field in ((Company, "bank_account"), (Customer, "party_bank_account")):
                manager = getattr(model, "all_objects", model.objects)
                qs = manager.exclude(**{field: ""}).exclude(**{f"{field}__startswith": "gcm1."})
                for row in qs.iterator():
                    total += 1
                    if not opts["dry_run"]:
                        row.save(update_fields=[field])
        verb = "would seal" if opts["dry_run"] else "sealed"
        self.stdout.write(f"{verb} {total} bank account value(s).")
