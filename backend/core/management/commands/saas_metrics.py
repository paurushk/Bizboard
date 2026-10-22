"""WP-PO2 / N9: print the month's SaaS numbers (staff). Usage: manage.py saas_metrics --month 2026-10"""

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Sign-ups, activation, trial-to-paid, churn, NRR, tickets per 100 tenants for one month."

    def add_arguments(self, parser):
        parser.add_argument("--month", default=timezone.localdate().strftime("%Y-%m"))

    def handle(self, *args, **opts):
        from core.rls import rls_bypass
        from support.health import monthly_metrics

        with rls_bypass():
            data = monthly_metrics(opts["month"])
        width = max(len(k) for k in data)
        for key, value in data.items():
            self.stdout.write(f"{key.ljust(width)}  {value if value is not None else '-'}")
