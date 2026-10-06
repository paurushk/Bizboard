"""Seal unsealed audit events into the hash chain (F-SEC-03). Run nightly."""

from django.core.management.base import BaseCommand

from core.models import AuditEvent
from core.services import audit_chain


class Command(BaseCommand):
    help = "Seal unsealed core.AuditEvent rows into the per-company hash chain."

    def handle(self, *args, **options):
        total = 0
        company_ids = set(
            AuditEvent.objects.filter(sealed_at__isnull=True).values_list("company_id", flat=True).distinct()
        )
        for cid in sorted(company_ids, key=lambda x: (x is None, x or 0)):
            n = audit_chain.seal(cid)
            total += n
        self.stdout.write(self.style.SUCCESS(f"Sealed {total} audit event(s) across {len(company_ids)} chain(s)."))
