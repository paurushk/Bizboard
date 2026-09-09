"""CR-120 and CR-144 data remediation management command.

Detects:
1. CR-120 dual-fulfillment: SalesOrders converted to both an invoice and a delivery challan.
2. CR-144 raw cost mutates: StockMovement cost drift without stamp_cost layer peel.
"""

from decimal import Decimal
import logging

from django.core.management.base import BaseCommand
from django.db import transaction

from inventory.models import MovementType, StockMovement
from sales.models import DeliveryChallan, SalesOrder

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Detect and heal CR-120 dual-fulfillment and CR-144 stock cost discrepancies."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=True,
            help="Dry run without mutating database (default: True).",
        )
        parser.add_argument(
            "--heal",
            action="store_true",
            default=False,
            help="Apply compensating adjustments for detected dual-fulfillments.",
        )
        parser.add_argument(
            "--company-id",
            type=int,
            default=None,
            help="Target a specific company ID (optional).",
        )

    def handle(self, *args, **options):
        dry_run = not options["heal"]
        target_company = options.get("company_id")

        self.stdout.write(f"=== Reconcile CR-120 / CR-144 (dry_run={dry_run}) ===")

        # ---------------- 1. CR-120 Dual Fulfillment ----------------
        so_qs = SalesOrder.objects.filter(converted_invoice__isnull=False)
        if target_company:
            so_qs = so_qs.filter(company_id=target_company)

        dual_so_count = 0
        duplicate_sale_movements = []

        for so in so_qs.select_related("converted_invoice", "company"):
            challans = list(
                DeliveryChallan.objects.filter(
                    sales_order=so, status=DeliveryChallan.Status.COMPLETED
                )
            )
            if not challans:
                continue

            dual_so_count += 1
            self.stdout.write(
                self.style.WARNING(
                    f"CR-120 Dual-fulfillment found: Company {so.company_id} | SO #{so.id} ({so.number}) "
                    f"has Invoice #{so.converted_invoice_id} and {len(challans)} completed challan(s)."
                )
            )

            inv_moves = list(
                StockMovement.objects.filter(
                    company_id=so.company_id,
                    reference_type="sales_invoice",
                    reference_id=str(so.converted_invoice_id),
                    movement_type=MovementType.SALE,
                )
            )
            for ch in challans:
                ch_moves = list(
                    StockMovement.objects.filter(
                        company_id=so.company_id,
                        reference_type="delivery_challan",
                        reference_id=str(ch.id),
                        movement_type=MovementType.SALE,
                    )
                )
                if inv_moves and ch_moves:
                    duplicate_sale_movements.extend(ch_moves)

        self.stdout.write(f"Dual-fulfilled SalesOrders detected: {dual_so_count}")
        self.stdout.write(f"Duplicate SALE movements detected: {len(duplicate_sale_movements)}")

        if not dry_run and duplicate_sale_movements:
            with transaction.atomic():
                healed = 0
                for move in duplicate_sale_movements:
                    from inventory.services import InventoryService

                    user = so.created_by
                    InventoryService.post_movement(
                        company=move.company,
                        warehouse=move.warehouse,
                        product=move.product,
                        movement_type=MovementType.ADJUSTMENT,
                        quantity=abs(move.quantity),
                        unit_cost=move.unit_cost,
                        reference_type="compensating_cr120",
                        reference_id=str(move.id),
                        user=user,
                    )
                    healed += 1
                self.stdout.write(self.style.SUCCESS(f"Healed {healed} duplicate stock movements."))

        # ---------------- 2. CR-144 Cost Stamp Audit ----------------
        mismatched_moves = 0
        from inventory.models import InventoryCostLayer

        move_qs = StockMovement.objects.filter(movement_type=MovementType.PURCHASE)
        if target_company:
            move_qs = move_qs.filter(company_id=target_company)

        for move in move_qs.iterator(chunk_size=500):
            layers = list(InventoryCostLayer.objects.filter(source_movement=move))
            if not layers:
                continue
            for layer in layers:
                if layer.unit_cost != move.unit_cost:
                    mismatched_moves += 1
                    if not dry_run:
                        StockMovement.stamp_cost(move.pk, unit_cost=layer.unit_cost)

        self.stdout.write(f"Mismatched cost movement layers: {mismatched_moves}")
        self.stdout.write(self.style.SUCCESS("Audit complete."))
