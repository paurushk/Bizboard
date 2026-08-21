from django.core.management.base import BaseCommand
from django.db import transaction

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
        if options["company"]:
            movements = movements.filter(company_id=options["company"])
        keys = list(
            movements.values_list(
                "company_id", "warehouse_id", "product_id", "batch_id"
            ).distinct()
        )
        company_ids = {k[0] for k in keys}
        warehouse_ids = {k[1] for k in keys if k[1]}
        product_ids = {k[2] for k in keys}
        batch_ids = {k[3] for k in keys if k[3]}

        companies = Company.objects.in_bulk(company_ids)
        warehouses = Warehouse.objects.in_bulk(warehouse_ids)
        products = Product.objects.in_bulk(product_ids)
        batches = BatchLot.objects.in_bulk(batch_ids)

        with transaction.atomic():
            for company_id, warehouse_id, product_id, batch_id in keys:
                InventoryService.rebuild_balance(
                    companies[company_id],
                    products[product_id],
                    warehouse=warehouses.get(warehouse_id),
                    batch=batches.get(batch_id) if batch_id else None,
                )
            # Drop orphan balance rows that have no movements (reserved must not
            # linger on keys that are no longer in the ledger).
            key_set = set(keys)
            orphan_qs = StockBalance.objects.all()
            if options["company"]:
                orphan_qs = orphan_qs.filter(company_id=options["company"])
            for bal in orphan_qs.iterator():
                key = (bal.company_id, bal.warehouse_id, bal.product_id, bal.batch_id)
                if key not in key_set:
                    bal.delete()

        self.stdout.write(self.style.SUCCESS(f"Rebuilt {len(keys)} stock balance rows."))
