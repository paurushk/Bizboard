from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from accounts.models import Company
from inventory.models import BatchLot, StockBalance, StockMovement, Warehouse
from inventory.services import InventoryService
from masters.models import Product


class Command(BaseCommand):
    help = "Rebuild derived stock balances from the append-only movement ledger."

    def add_arguments(self, parser):
        parser.add_argument("--company", type=int, help="Limit rebuild to a company id.")

    def handle(self, *args, **options):
        movements = StockMovement.objects.all()
        balance_qs = StockBalance.objects.all()
        if options["company"]:
            movements = movements.filter(company_id=options["company"])
            balance_qs = balance_qs.filter(company_id=options["company"])
        keys = list(
            movements.values_list(
                "company_id", "warehouse_id", "product_id", "batch_id"
            ).distinct()
        )
        keys_by_company = {}
        for key in keys:
            keys_by_company.setdefault(key[0], []).append(key)

        # A company with StockBalance rows but zero movements (stray/orphan
        # cache with nothing backing it) still needs its balances swept —
        # include those company ids even though they have no rebuild keys.
        balance_company_ids = set(balance_qs.values_list("company_id", flat=True).distinct())
        all_company_ids = set(keys_by_company) | balance_company_ids

        warehouse_ids = {k[1] for k in keys if k[1]}
        product_ids = {k[2] for k in keys}
        batch_ids = {k[3] for k in keys if k[3]}

        companies = Company.objects.in_bulk(all_company_ids)
        warehouses = Warehouse.objects.in_bulk(warehouse_ids)
        products = Product.objects.in_bulk(product_ids)
        batches = BatchLot.objects.in_bulk(batch_ids)

        # B8-022: was one transaction.atomic() around every key for every
        # company in scope — a long-held single transaction (lock
        # contention, idle_in_transaction_session_timeout risk) with
        # O(keys × queries) and no progress output. Commit per company
        # instead, and batch the orphan delete into one query per company
        # rather than an iterator + per-row .delete().
        #
        # B8-023: rebuild_balance no longer side-effects every batch-lot row
        # of a product as part of rebuilding some other key — reservation
        # reconciliation for batch-tracked products is now a second pass,
        # once per (company, product, warehouse), run after every key's
        # on_hand has been rebuilt (fefo_batches() only sees lots with
        # on_hand > 0, so on_hand must be correct first).
        for company_id in all_company_ids:
            company = companies[company_id]
            company_keys = keys_by_company.get(company_id, [])
            with transaction.atomic():
                for _cid, warehouse_id, product_id, batch_id in company_keys:
                    InventoryService.rebuild_balance(
                        company,
                        products[product_id],
                        warehouse=warehouses.get(warehouse_id),
                        batch=batches.get(batch_id) if batch_id else None,
                    )
                reconcile_scopes = {
                    (warehouse_id, product_id)
                    for _cid, warehouse_id, product_id, _batch_id in company_keys
                    if products[product_id].track_batch
                }
                for warehouse_id, product_id in reconcile_scopes:
                    InventoryService.reconcile_batch_reservations(
                        company, products[product_id], warehouse=warehouses.get(warehouse_id),
                    )
                # Drop orphan balance rows that have no movements (reserved
                # must not linger on keys no longer in the ledger) — one
                # query instead of an iterator with a per-row delete.
                orphan_qs = StockBalance.objects.filter(company_id=company_id)
                company_key_set = {
                    (warehouse_id, product_id, batch_id)
                    for _cid, warehouse_id, product_id, batch_id in company_keys
                }
                if company_key_set:
                    exclude_q = Q()
                    for warehouse_id, product_id, batch_id in company_key_set:
                        exclude_q |= Q(warehouse_id=warehouse_id, product_id=product_id, batch_id=batch_id)
                    orphan_qs = orphan_qs.exclude(exclude_q)
                orphan_qs.delete()
            self.stdout.write(f"company {company_id}: {len(company_keys)} stock balance rows rebuilt")

        self.stdout.write(self.style.SUCCESS(f"Rebuilt {len(keys)} stock balance rows."))
