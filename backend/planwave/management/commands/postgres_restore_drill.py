"""Checklist for the Postgres restore drill.

The drill itself runs on a non-production copy of the host chosen in WI-069.
This command refuses to report success until that host and a timed log exist.
"""

import os

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Check that a Postgres restore drill has been recorded. Does not invent a result."

    def handle(self, *args, **options):
        host = os.environ.get("POSTGRES_DRILL_HOST", "").strip()
        log = os.environ.get("POSTGRES_DRILL_LOG", "").strip()
        self.stdout.write("Steps: restore WAL to the chosen time, then restore the encrypted dump, and time both.")
        self.stdout.write("Target: RPO 5 minutes, RTO 1 hour. A wrong key must fail.")
        if not host or not log or not os.path.isfile(log):
            raise CommandError(
                "WI-069 is still open. Set POSTGRES_DRILL_HOST and POSTGRES_DRILL_LOG to a real drill log."
            )
        self.stdout.write(f"Drill log present for {host}: {log}")
