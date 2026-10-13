"""Summarise bill-import health: failures, time to commit, how much gets edited."""

from django.core.management.base import BaseCommand

from imports import metrics


class Command(BaseCommand):
    help = "Print bill import statistics for the last N days (default 30)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30)
        parser.add_argument("--company-id", type=int, default=None)

    def handle(self, *args, **options):
        days = options["days"]
        for row in metrics.summary(days, options["company_id"]):
            total = row["uploads"]
            self.stdout.write(f"== {row['kind']} (last {days} days): {total} upload(s)")
            self.stdout.write(f"   by status: {row['by_status']}")
            rate = row["failure_rate"]
            self.stdout.write(f"   extraction failure rate: {rate:.0%}" if rate is not None else "   extraction failure rate: n/a")
            if row["committed"]:
                self.stdout.write(f"   mean time upload -> draft: {row['mean_minutes_to_draft']:.1f} min")
                self.stdout.write(f"   lines edited by the reviewer: {row['edited_share']:.0%}")
                self.stdout.write(f"   lines left out: {row['excluded_share']:.0%}")
            if row["rejected_commits"] is not None:
                self.stdout.write(f"   commits refused for fixable problems (all bill kinds): {row['rejected_commits']}")
