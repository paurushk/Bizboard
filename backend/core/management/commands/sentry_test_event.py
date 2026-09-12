"""Send one test event to Sentry, so "Sentry DSN + on-call routing live"
(a Go/No-Go Final Gate) is a single command an operator runs after setting
SENTRY_DSN, instead of an open-ended "verify it somehow".

    SENTRY_DSN=https://... python manage.py sentry_test_event

Refuses (with a clear message, not a stack trace) when SENTRY_DSN isn't set,
so a forgotten env var reads as "not configured" rather than an error.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Send a single test event to Sentry to verify SENTRY_DSN + alert routing are live."

    def handle(self, *args, **options):
        if not getattr(settings, "SENTRY_DSN", ""):
            raise CommandError(
                "SENTRY_DSN is not set — nothing to send. Set it and re-run this command "
                "as the ENV_CHECKLIST.md evidence step for the Sentry Final Gate."
            )

        try:
            import sentry_sdk
        except ImportError as exc:
            raise CommandError("SENTRY_DSN is set but sentry-sdk is not installed.") from exc

        event_id = sentry_sdk.capture_message(
            "Bizboard Sentry test event (manage.py sentry_test_event)", level="info"
        )
        sentry_sdk.flush(timeout=5)
        self.stdout.write(self.style.SUCCESS(f"Sent Sentry test event {event_id}. Check the Sentry project now."))
