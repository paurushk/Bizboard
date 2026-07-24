"""Optional demo seed: python manage.py seed_demo"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Company, CompanyUser, User
from inventory.models import MovementType
from inventory.services import InventoryService
from masters.models import Customer, Product, Supplier, Unit


DEFAULT_TERMS = (
    "1. Goods once sold will not be taken back or exchanged.\n"
    "2. All disputes are subject to Bengaluru jurisdiction only.\n"
    "3. Please pay via UPI or bank transfer within 7 days."
)


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
            name="Demo Traders",
            legal_name="Demo Traders Pvt Ltd",
            gstin="29ABCDE1234F1Z5",
            state="Karnataka",
            address="12, MG Road",
            city="Bengaluru",
            pincode="560001",
            phone="08041234567",
            email="billing@demotraders.local",
            upi_id="demotraders@upi",
            invoice_terms=DEFAULT_TERMS,
        )
        CompanyUser.objects.create(
            company=company, user=user, role=CompanyUser.Role.OWNER,
            can_manage_inventory=True, can_import=True,
            can_cancel_documents=True, can_view_financial_reports=True, can_export=True,
        )
        unit = Unit.objects.create(company=company, name="Piece", short_name="pcs")
        strip = Unit.objects.create(company=company, name="Strip", short_name="str")
        customer = Customer.objects.create(
            company=company,
            name="Sharma Medicals",
            state="Karnataka",
            phone="9876543210",
            email="sharma@example.com",
            gstin="29AABCU9603R1ZM",
            billing_address="45, Commercial Street, Bengaluru 560001",
            shipping_address="45, Commercial Street, Bengaluru 560001",
        )
        supplier = Supplier.objects.create(
            company=company, name="Wholesale Depot", state="Karnataka",
            phone="9988776655", gstin="29AAACW3775F1Z2",
        )
        products = [
            Product(
                company=company, name="Paracetamol 500mg", sku="MED-PCM-500",
                barcode="890100100001", hsn_code="3004", gst_rate=Decimal("12"),
                purchase_price=Decimal("18"), selling_price=Decimal("25"),
                mrp=Decimal("30"), unit=strip, reorder_level=Decimal("20"),
            ),
            Product(
                company=company, name="Digital Thermometer", sku="MED-THM-01",
                barcode="890100100002", hsn_code="9025", gst_rate=Decimal("18"),
                purchase_price=Decimal("120"), selling_price=Decimal("180"),
                mrp=Decimal("249"), unit=unit, reorder_level=Decimal("5"),
            ),
            Product(
                company=company, name="Demo Widget", sku="DEMO-1",
                barcode="890000000001", hsn_code="8471", gst_rate=Decimal("18"),
                purchase_price=Decimal("80"), selling_price=Decimal("100"),
                mrp=Decimal("120"), unit=unit, reorder_level=Decimal("5"),
            ),
        ]
        Product.objects.bulk_create(products)
        for product in Product.objects.filter(company=company):
            InventoryService.post_movement(
                company=company, product=product,
                movement_type=MovementType.OPENING_STOCK,
                quantity=Decimal("100"), unit_cost=product.purchase_price, user=user,
            )
        self.stdout.write(self.style.SUCCESS(
            f"Seeded Demo Traders. Login: {user.email} / DemoPass123! "
            f"(customer={customer.id}, supplier={supplier.id}, products={Product.objects.filter(company=company).count()})"
        ))
