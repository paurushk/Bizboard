"""List customer receipts that break the Money In input rules. Read-only: it changes nothing.

Run before deploying the Phase 2 rules, so the owner can review what the new validation would
have refused: a CREDIT-mode receipt, UPI/bank/card money with no bank account, a settlement
discount larger than the amount received, or a discount that was never applied to any invoice.
"""

from django.core.management.base import BaseCommand
from django.db.models import Count, F, Q

from payments.models import CustomerReceipt, PaymentMode, ReceiptStatus

RULES = (
    ("credit_mode", "Mode is CREDIT (not a way of being paid)"),
    ("bank_mode_without_bank", "UPI, bank or card money with no bank account"),
    ("discount_above_amount", "Settlement discount is more than the amount received"),
    ("discount_never_applied", "Settlement discount on a receipt that clears no invoice"),
)


class Command(BaseCommand):
    help = "Report receipts that break the Money In rules (CREDIT mode, bank-less bank money, odd discounts)."

    def add_arguments(self, parser):
        parser.add_argument("--company", type=int, help="Only this company id.")

    def handle(self, *args, **options):
        live = CustomerReceipt.objects.exclude(
            status__in=(ReceiptStatus.VOIDED, ReceiptStatus.REFUNDED)
        )
        if options.get("company"):
            live = live.filter(company_id=options["company"])
        checks = {
            "credit_mode": live.filter(mode=PaymentMode.CREDIT),
            "bank_mode_without_bank": live.filter(
                mode__in=(PaymentMode.UPI, PaymentMode.BANK, PaymentMode.CARD), bank_account__isnull=True
            ),
            "discount_above_amount": live.filter(settlement_discount__gt=F("amount")),
            "discount_never_applied": live.filter(settlement_discount__gt=0)
            .annotate(
                live_allocations=Count("allocations", filter=Q(allocations__reversed_at__isnull=True))
            )
            .filter(live_allocations=0),
        }
        total = 0
        for key, label in RULES:
            rows = checks[key].select_related("company", "customer").order_by("company_id", "id")
            count = rows.count()
            total += count
            self.stdout.write(f"\n{label}: {count}")
            for rec in rows[:200]:
                self.stdout.write(
                    f"  company={rec.company_id} receipt={rec.id} number={rec.number} "
                    f"date={rec.receipt_date} mode={rec.mode} amount={rec.amount} "
                    f"discount={rec.settlement_discount} customer={rec.customer_id}"
                )
            if count > 200:
                self.stdout.write(f"  ... and {count - 200} more")
        self.stdout.write(f"\n{total} finding(s). Nothing was changed.")
