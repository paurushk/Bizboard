from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Company
from insights.services import generate_daily_summary, snapshot_health


class Command(BaseCommand):
    help = "Generate daily business summaries and health snapshots for AI-enabled companies."

    def handle(self, *args, **options):
        today = timezone.localdate()
        n = 0
        failed = 0
        for company in Company.objects.filter(ai_features_enabled=True):
            # B9-042: one tenant with bad data must not abort the run for all
            # subsequent tenants (the Celery fan-out path is already isolated).
            try:
                generate_daily_summary(company, for_date=today)
                snapshot_health(company, as_of=today)
                n += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                self.stderr.write(f"insights failed for company {company.pk}: {exc}")
        self.stdout.write(
            self.style.SUCCESS(f"Generated insights for {n} companies on {today}")
        )
        if failed:
            raise SystemExit(1)
