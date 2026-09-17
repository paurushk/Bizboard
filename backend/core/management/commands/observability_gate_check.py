"""Print O-Gate 1+2 engineering status. Does not close Human Sentry/on-call.

    python manage.py observability_gate_check
    python manage.py observability_gate_check --request-id <uuid>
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand

from core.observability import hash_id
from insights.models import ShopFloorEvent


class Command(BaseCommand):
    help = "Report O-Gate 1+2 code status and remaining Human steps."

    def add_arguments(self, parser):
        parser.add_argument(
            "--request-id",
            default="",
            help="Grep ShopFloorEvent.request_id (no PII columns printed).",
        )

    def handle(self, *args, **options):
        dsn = bool((getattr(settings, "SENTRY_DSN", "") or "").strip())
        token = bool((getattr(settings, "METRICS_TOKEN", "") or "").strip())
        cols = {f.name for f in ShopFloorEvent._meta.get_fields()}
        envelope = {
            "journey",
            "feature",
            "role",
            "session_id",
            "request_id",
            "success",
            "failure_reason",
        }
        missing = sorted(envelope - cols)
        self.stdout.write("O-Gate engineering check")
        self.stdout.write(f"  sentry_configured={dsn}  (DSN never printed)")
        self.stdout.write(f"  metrics_token_set={token}")
        self.stdout.write(f"  company_hash_column={'company_hash' in cols}")
        self.stdout.write(f"  envelope_columns_missing={missing or 'none'}")
        self.stdout.write(f"  hash_id(1)={hash_id(1)}")

        rid = (options.get("request_id") or "").strip()
        if rid:
            rows = list(
                ShopFloorEvent.objects.filter(request_id=rid).values(
                    "event", "journey", "success", "failure_reason", "request_id", "session_id"
                )[:20]
            )
            self.stdout.write(f"  shopfloor_matches={len(rows)}")
            for row in rows:
                self.stdout.write(f"    {row}")

        self.stdout.write("")
        self.stdout.write("Human remaining (docs/ops/OGATE_HUMAN.md):")
        self.stdout.write("  OG1-H1 Sentry project")
        self.stdout.write("  OG1-H2 SENTRY_DSN / VITE_SENTRY_DSN / SENTRY_RELEASE on host")
        self.stdout.write("  OG1-H3 fill docs/ops/ONCALL_ROSTER.md")
        self.stdout.write("  OG1-H4 python manage.py sentry_test_event + page received")
        self.stdout.write("  OG1-H5 scrape GET /metrics with Bearer METRICS_TOKEN")
        self.stdout.write("  OG2 walk docs/ops/OGATE_GREP_WALK.md")
