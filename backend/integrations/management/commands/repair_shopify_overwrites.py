"""List Shopify stock adjustments that landed before the hold rule.

Those movements do not store the quantity from before the webhook. This
command does not guess it. --apply posts one adjustment through
InventoryService only when the operator passes the on-hand to restore.
"""

from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Company
from core.rls import rls_bypass
from inventory.models import MovementType, StockBalance, StockMovement, Warehouse
from masters.models import Product


class Command(BaseCommand):
    help = (
        "List Shopify adjustment movements. --apply sets on-hand to --on-hand "
        "for one product and warehouse. The previous quantity is not guessed."
    )

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--product-id", type=int)
        parser.add_argument("--warehouse-id", type=int)
        parser.add_argument("--on-hand", dest="on_hand")

    def handle(self, *args, **options):
        with rls_bypass():
            company = Company.objects.filter(pk=options["company_id"]).first()
            if company is None:
                raise CommandError("No such company.")
            movements = StockMovement.objects.filter(
                company=company,
                movement_type=MovementType.ADJUSTMENT,
                reference_type="shopify",
            ).order_by("id")
            self.stdout.write(f"shopify_adjustments={movements.count()}")
            for row in movements:
                self.stdout.write(
                    f"  movement={row.pk} product={row.product_id} warehouse={row.warehouse_id} "
                    f"quantity={row.quantity}"
                )
            if not options["apply"]:
                self.stdout.write("dry-run")
                return
            product_id = options["product_id"]
            warehouse_id = options["warehouse_id"]
            raw_on_hand = options["on_hand"]
            if product_id is None or warehouse_id is None or raw_on_hand in (None, ""):
                raise CommandError(
                    "Pass --product-id, --warehouse-id, and --on-hand. "
                    "The overwritten quantity is not stored on the movement."
                )
            try:
                target = Decimal(str(raw_on_hand))
            except (InvalidOperation, ValueError) as exc:
                raise CommandError("--on-hand must be a number.") from exc
            if target < 0:
                raise CommandError("--on-hand cannot be negative.")
            product = Product.objects.filter(company=company, pk=product_id).first()
            if product is None:
                raise CommandError("That product is not on this company.")
            warehouse = Warehouse.objects.filter(company=company, pk=warehouse_id).first()
            if warehouse is None:
                raise CommandError("That warehouse is not on this company.")
            shopify_posted = StockMovement.objects.filter(
                company=company,
                product=product,
                warehouse=warehouse,
                movement_type=MovementType.ADJUSTMENT,
                reference_type="shopify",
            ).exists()
            if not shopify_posted:
                raise CommandError(
                    "No Shopify adjustment exists for that product and warehouse. No stock was changed."
                )
            from inventory.services import InventoryService

            with transaction.atomic():
                balance = (
                    StockBalance.objects.select_for_update()
                    .filter(company=company, product=product, warehouse=warehouse)
                    .first()
                )
                current = balance.on_hand if balance is not None else Decimal("0")
                delta = target - current
                if delta == 0:
                    self.stdout.write(f"on_hand already {target}. No movement posted.")
                    return
                InventoryService.post_movement(
                    company=company,
                    product=product,
                    warehouse=warehouse,
                    movement_type=MovementType.ADJUSTMENT,
                    quantity=delta,
                    reason="Repair Shopify overwrite",
                    reference_type="shopify_repair",
                    reference_id=str(product.pk),
                )
            self.stdout.write(f"posted delta={delta} on_hand={target} product={product.pk}")
