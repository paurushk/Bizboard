"""Delete HelpEvent rows older than N days (default 180)."""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import HelpEvent
from core.rls import rls_bypass


class Command(BaseCommand):
    help = "Delete HelpEvent rows older than --days (default 180)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=180)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        days = max(1, int(options["days"]))
        cutoff = timezone.now() - timedelta(days=days)
        # B7-003: HelpEvent FORCE-RLS's on app.company_id, which is unset for a
        # management command — without rls_bypass() this deletes nothing. Matches
        # the prune_help_events_task Celery twin.
        with rls_bypass():
            qs = HelpEvent.objects.filter(created_at__lt=cutoff)
            count = qs.count()
            if options["dry_run"]:
                self.stdout.write(f"Would delete {count} HelpEvent rows older than {days} days.")
                return
            deleted, _ = qs.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} HelpEvent rows older than {days} days."))
