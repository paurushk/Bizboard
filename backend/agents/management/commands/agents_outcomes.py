"""Print the Collections outcome report for one company: manage.py agents_outcomes <company_id> [--days 30]."""

import json
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import Company
from agents.outcomes import collections_outcomes


class Command(BaseCommand):
    help = "Read-only report: did Collections drafts lead to receipts within 7 days?"

    def add_arguments(self, parser):
        parser.add_argument("company_id", type=int)
        parser.add_argument("--days", type=int, default=30)

    def handle(self, *args, **opts):
        company = Company.objects.filter(pk=opts["company_id"]).first()
        if company is None:
            raise CommandError("No such company.")
        since = timezone.now() - timedelta(days=opts["days"])
        report = collections_outcomes(company, since=since)
        self.stdout.write(json.dumps(report, indent=2))
