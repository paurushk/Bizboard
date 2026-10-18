"""Write ``SalesInvoice.opportunity`` for invoices made before the link existed.

Walks the quotation -> order -> challan -> invoice chain (``crm.revenue.chain_invoice_ids``).
Dry-run by default; pass ``--apply`` to write. An invoice that already has a link is left alone,
and an invoice reached from two different deals is reported and skipped.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from crm.models import Opportunity
from crm.revenue import chain_invoice_ids
from sales.models import SalesInvoice


class Command(BaseCommand):
    help = "Link existing invoices to the CRM deal they came from (dry-run unless --apply)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Write the links (default is a dry run).")
        parser.add_argument("--company", type=int, default=None, help="Only this company id.")

    def handle(self, *args, **options):
        apply = options["apply"]
        deals = Opportunity.objects.all()
        if options["company"]:
            deals = deals.filter(company_id=options["company"])
        by_company: dict[int, list[int]] = {}
        for deal_id, company_id in deals.values_list("id", "company_id"):
            by_company.setdefault(company_id, []).append(deal_id)
        linked = skipped_conflict = already = 0
        for company_id, deal_ids in by_company.items():
            owner_of: dict[int, set[int]] = {}
            for deal_id, invoice_ids in chain_invoice_ids(company_id, deal_ids).items():
                for invoice_id in invoice_ids:
                    owner_of.setdefault(invoice_id, set()).add(deal_id)
            current = dict(
                SalesInvoice.objects.filter(company_id=company_id, pk__in=list(owner_of))
                .values_list("id", "opportunity_id")
            )
            for invoice_id, owners in owner_of.items():
                if current.get(invoice_id):
                    already += 1
                elif len(owners) != 1:
                    skipped_conflict += 1
                    self.stdout.write(f"skip invoice {invoice_id}: reached from deals {sorted(owners)}")
                else:
                    linked += 1
                    if apply:
                        SalesInvoice.objects.filter(pk=invoice_id, opportunity__isnull=True).update(
                            opportunity_id=next(iter(owners)),
                        )
        mode = "applied" if apply else "dry run (use --apply to write)"
        self.stdout.write(
            f"{mode}: {linked} to link, {already} already linked, {skipped_conflict} skipped (ambiguous)"
        )
