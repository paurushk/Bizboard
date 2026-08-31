from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Retry books for gateway captures parked as CAPTURED_PENDING_BOOKS (W0-03)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, default=None)
        parser.add_argument("--older-than-minutes", type=int, default=5)

    def handle(self, *args, **options):
        from payments.services import PaymentService

        posted, attempted = PaymentService.reconcile_gateway_captures(
            company_id=options["company_id"],
            older_than_minutes=options["older_than_minutes"],
        )
        self.stdout.write(f"holding retries attempted={attempted} posted={posted}")
