"""Remove the per-invoice / per-promise attention state that migration 0015 copied to AR_CUSTOMER keys.

Run this one release after the merged customer row has shipped, when nobody needs to roll back.
It only deletes an old row whose customer already has an ``AR_CUSTOMER:<id>`` row. Without
``--apply`` it only reports what it would remove.

    python manage.py attention_cleanup_old_keys            # report
    python manage.py attention_cleanup_old_keys --apply    # delete
"""

from django.core.management.base import BaseCommand
from django.db.models import Q

from insights.models import AttentionOutcome, AttentionRowState

SOURCE_CODES = ("AR_COLLECTION_RISK", "PREDICTED_LATE_PAYMENT", "PROMISE_TO_PAY_DUE", "CREDIT_LIMIT_NEAR")


def _old_key_q() -> Q:
    q = Q()
    for code in SOURCE_CODES:
        q |= Q(dedupe_key__startswith=f"{code}:")
    return q


class Command(BaseCommand):
    help = "Delete attention state under the old receivable keys once the merged customer row has them."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Delete. Without it, only report.")

    def handle(self, *args, **options):
        from payments.models import PaymentPromise
        from sales.models import SalesInvoice

        apply = options["apply"]
        removable = {"state": [], "outcome": []}
        for label, model in (("state", AttentionRowState), ("outcome", AttentionOutcome)):
            have = set(
                model.objects.filter(dedupe_key__startswith="AR_CUSTOMER:").values_list("company_id", "dedupe_key")
            )
            for row in model.objects.filter(_old_key_q()).iterator():
                customer_id = self._customer_id(row, SalesInvoice, PaymentPromise)
                if customer_id and (row.company_id, f"AR_CUSTOMER:{customer_id}") in have:
                    removable[label].append(row.pk)
        for label, model in (("state", AttentionRowState), ("outcome", AttentionOutcome)):
            ids = removable[label]
            self.stdout.write(f"{label}: {len(ids)} old row(s) with a merged copy")
            if apply and ids:
                model.objects.filter(pk__in=ids).delete()
        self.stdout.write("deleted" if apply else "dry run: nothing deleted (use --apply)")

    @staticmethod
    def _customer_id(row, SalesInvoice, PaymentPromise):
        code, _, rest = row.dedupe_key.partition(":")
        if code in ("AR_COLLECTION_RISK", "CREDIT_LIMIT_NEAR"):
            parts = rest.split(":")
            return int(parts[1]) if len(parts) == 2 and parts[0] == "customer" and parts[1].isdigit() else None
        if not rest.isdigit():
            return None
        if code == "PREDICTED_LATE_PAYMENT":
            return SalesInvoice.objects.filter(company_id=row.company_id, pk=int(rest)).values_list("customer_id", flat=True).first()
        if code == "PROMISE_TO_PAY_DUE":
            return PaymentPromise.objects.filter(company_id=row.company_id, pk=int(rest)).values_list("customer_id", flat=True).first()
        return None
