"""Run locally (full repo checkout) to refresh the committed fallback
snapshot Coverage Copilot reads when running in a container that only has
backend/ on disk: python manage.py refresh_coverage_snapshot
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from ops.coverage_scan import SNAPSHOT_PATH, _repo_root, scan


class Command(BaseCommand):
    help = "Refresh ops/data/coverage_snapshot.json from a live repo scan (run locally, not in a container)."

    def handle(self, *args, **options):
        if _repo_root() is None:
            raise CommandError(
                "No web/ + qos/ siblings found next to backend/ — this must "
                "run against a full repo checkout, not a container with only "
                "backend/ baked in."
            )
        result = scan()
        result.pop("source", None)
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"wrote {SNAPSHOT_PATH}"))
