"""WP-ID1: start a staff-assisted owner recovery (step 1 of 2). Runbook: docs/ops/OWNER_RECOVERY.md.

    manage.py owner_recovery request --company 12 --staff you@bizboard --ticket 345 \
        --email owner@business.in --proof "GST portal email matches" --reason "Owner lost phone"

A second, different staff member approves in Django admin (Ownership transfers -> Approve).
"""

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Start a staff-assisted owner recovery for a company whose owner can't sign in."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["request"])
        parser.add_argument("--company", type=int, required=True)
        parser.add_argument("--staff", required=True, help="Your staff email")
        parser.add_argument("--ticket", type=int, required=True, help="Platform support ticket id")
        parser.add_argument("--email", required=True, help="Address the business proved it controls")
        parser.add_argument("--proof", required=True, help="What proof you checked")
        parser.add_argument("--reason", required=True)

    def handle(self, *args, **o):
        from accounts.models import Company, User
        from accounts.ownership import request_recovery
        from core.exceptions import BusinessRuleError
        from core.rls import rls_bypass
        from support.models import PlatformTicket

        with rls_bypass():
            company = Company.objects.filter(pk=o["company"]).first()
            staff = User.objects.filter(email__iexact=o["staff"], is_staff=True).first()
            ticket = PlatformTicket.objects.filter(pk=o["ticket"], company=company).first()
            if company is None or staff is None:
                raise CommandError("Unknown company, or that email is not a staff user.")
            if ticket is None:
                raise CommandError("That ticket does not exist for this company.")
            try:
                t = request_recovery(company=company, staff_user=staff, ticket=ticket,
                                     recovery_email=o["email"], proof_note=o["proof"], reason=o["reason"])
            except BusinessRuleError as exc:
                raise CommandError(str(exc)) from exc
        self.stdout.write(f"Recovery {t.pk} requested. A second staff member must approve it in Django admin.")
