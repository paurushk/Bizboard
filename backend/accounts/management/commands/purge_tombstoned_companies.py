"""SR-40 / D13 — hard-delete tombstoned companies past the 8-year GST window.

Run daily (celery-beat or cron). A tombstone is a company with ``erased_at``
set; once ``erased_at`` is older than the retention window its retained tax
documents are hard-deleted along with the company row.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Hard-purge tombstoned companies whose GST retention window has elapsed."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        from django.utils import timezone

        from accounts.erasure import GST_RETENTION, purge_expired_tombstones
        from accounts.models import Company

        if options["dry_run"]:
            cutoff = timezone.now() - GST_RETENTION
            due = Company.objects.filter(erased_at__isnull=False, erased_at__lt=cutoff)
            self.stdout.write(f"[dry-run] {due.count()} tombstoned compan(y|ies) due for purge.")
            for c in due:
                self.stdout.write(f"  id={c.pk} erased_at={c.erased_at.isoformat()}")
            return

        n = purge_expired_tombstones()
        self.stdout.write(self.style.SUCCESS(f"Purged {n} expired tombstone(s)."))
