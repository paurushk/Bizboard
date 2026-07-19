"""Optional demo seed: python manage.py seed_demo"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Company, CompanyUser, User
from inventory.models import MovementType
from inventory.services import InventoryService
from masters.models import Customer, Product, Supplier, Unit


class Command(BaseCommand):
    help = "Seed a demo company with sample masters and opening stock."

    @transaction.atomic
    def handle(self, *args, **options):
        if Company.objects.filter(name="Demo Traders").exists():
            self.stdout.write("Demo Traders already exists — skipping.")
            return

        user = User.objects.create_user(
            email="demo@bizboard.local", password="DemoPass123!",
            full_name="Demo Owner", phone="9000000001",
        )
        company = Company.objects.create(
            name="Demo Traders", legal_name="Demo Traders Pvt Ltd",
            gstin="29ABCDE1234F1Z5", state="Karnataka",
            address="MG Road, Bengaluru", upi_id="demo@upi",
        )
        CompanyUser.objects.create(
            company=company, user=user, role=CompanyUser.Role.OWNER,
            can_manage_inventory=True, can_import=True,
        )
        unit = Unit.objects.create(company=company, name="Piece", short_name="pcs")
        customer = Customer.objects.create(
            company=company, name="Walk-in Customer", state="Karnataka",
        )
        supplier = Supplier.objects.create(
            company=company, name="Wholesale Depot", state="Karnataka",
        )
        product = Product.objects.create(
            company=company, name="Demo Widget", sku="DEMO-1", barcode="890000000001",
            hsn_code="8471", gst_rate=Decimal("18"), purchase_price=Decimal("80"),
            selling_price=Decimal("100"), unit=unit, reorder_level=Decimal("5"),
        )
        InventoryService.post_movement(
            company=company, product=product,
            movement_type=MovementType.OPENING_STOCK,
            quantity=Decimal("100"), unit_cost=Decimal("80"), user=user,
        )
        self.stdout.write(self.style.SUCCESS(
            f"Seeded Demo Traders. Login: {user.email} / DemoPass123! "
            f"(customer={customer.id}, supplier={supplier.id}, product={product.id})"
        ))
