"""Optional demo seed: python manage.py seed_demo [--with-activity]

``--with-activity`` (BB-134) adds three months of believable trading through the real services
so a demo's dashboard, outstanding, aging and GSTR-1 worksheet are not empty: GST invoices to a
local, an inter-state and a walk-in customer, receipts that leave some bills paid, some part-paid
and some outstanding, and one sales return. Every document is tagged ``DEMO:<n>``, so re-running
skips what exists. Demo script: docs/onboarding/DEMO_SCRIPT.md.
"""

from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

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
    help = "Seed a demo company with sample masters and opening stock (--with-activity adds sales)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--with-activity",
            action="store_true",
            help="Also create three months of invoices, receipts and a return (idempotent).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        _env = getattr(settings, "DJANGO_ENV", "").strip().lower()
        # B6-016: never seed test data on a shared/real deployment.
        if _env in ("production", "staging") or not getattr(settings, "DEBUG", False):
            raise CommandError(
                "seed_demo refuses to run outside DEBUG / non-prod (DJANGO_ENV={}).".format(_env or "unset")
            )

        if Company.objects.filter(name="Demo Traders").exists():
            # UXW2-005 / UXW2-010: repair demo tax defaults on re-seed without wiping data.
            company = Company.objects.filter(name="Demo Traders").first()
            updates = []
            if company.gstin in ("", "29ABCDE1234F1Z5") or (
                company.gstin and len(company.gstin) == 15 and company.gstin.endswith("1Z5")
            ):
                company.gstin = "29ABCDE1234F1ZW"
                updates.append("gstin")
            if not company.assume_local_state_for_blank_party:
                company.assume_local_state_for_blank_party = True
                updates.append("assume_local_state_for_blank_party")
            if company.negative_stock_policy != Company.NegativeStockPolicy.BLOCK:
                company.negative_stock_policy = Company.NegativeStockPolicy.BLOCK
                updates.append("negative_stock_policy")
            if company.tax_profile_confirmed_at is None:
                company.tax_profile_confirmed_at = timezone.now()
                updates.append("tax_profile_confirmed_at")
            if updates:
                company.save(update_fields=updates)
                self.stdout.write(f"Demo Traders updated fields: {', '.join(updates)}")
            else:
                self.stdout.write("Demo Traders already exists — skipping.")
            if options.get("with_activity"):
                self._activity(company)
            return

        user = User.objects.create_user(
            email="demo@bizboard.local", password="DemoPass123!",
            full_name="Demo Owner", phone="9000000001",
        )
        company = Company.objects.create(
            name="Demo Traders",
            legal_name="Demo Traders Pvt Ltd",
            gstin="29ABCDE1234F1ZW",
            state="Karnataka",
            address="12, MG Road",
            city="Bengaluru",
            pincode="560001",
            phone="08041234567",
            email="billing@demotraders.local",
            upi_id="demotraders@upi",
            invoice_terms=DEFAULT_TERMS,
            assume_local_state_for_blank_party=True,
            negative_stock_policy=Company.NegativeStockPolicy.BLOCK,
            tax_profile_confirmed_at=timezone.now(),
        )
        CompanyUser.objects.create(
            company=company, user=user, role=CompanyUser.Role.OWNER,
            can_manage_inventory=True, can_import=True,
            can_cancel_documents=True, can_view_financial_reports=True, can_export=True,
            can_create_sales=True, can_create_purchases=True, can_create_payments=True,
            can_post_journals=True,
        )
        unit = Unit.objects.create(company=company, name="Piece", short_name="pcs")
        strip = Unit.objects.create(company=company, name="Strip", short_name="str")
        customer = Customer.objects.create(
            company=company,
            name="Sharma Medicals",
            state="Karnataka",
            phone="9876543210",
            email="sharma@example.com",
            gstin="29AABCU9603R1ZJ",
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
        if options.get("with_activity"):
            self._activity(company)

    def _activity(self, company):
        from datetime import timedelta

        from core.seed_guard import seed_load_scope
        from payments.models import PaymentAllocation
        from payments.services import PaymentService
        from sales.models import SalesInvoice, SalesReturn
        from sales.return_service import ReturnService
        from sales.services import SalesService

        owner = CompanyUser.objects.filter(company=company, role=CompanyUser.Role.OWNER).order_by("id").first().user
        local = Customer.objects.filter(company=company, name="Sharma Medicals").first()
        interstate, _ = Customer.objects.get_or_create(
            company=company, name="Patel Pharma Distributors",
            defaults={"state": "Maharashtra", "phone": "9822001100", "gstin": "27AAFCP1234Q1ZB",
                      "billing_address": "8, Kalbadevi Road, Mumbai 400002"},
        )
        walk_in, _ = Customer.objects.get_or_create(
            company=company, name="Walk-in Customer", defaults={"state": "Karnataka"},
        )
        products = list(Product.objects.filter(company=company).order_by("id"))
        today = timezone.localdate()
        made = paid = returned = 0
        with seed_load_scope():
            for n in range(24):
                note = f"DEMO:{n:02d}"
                customer = (local, interstate, walk_in)[n % 3]
                invoice = SalesInvoice.objects.filter(company=company, notes=note).first()
                if invoice is None:
                    invoice = SalesInvoice.objects.create(
                        company=company, customer=customer,
                        invoice_type=SalesInvoice.InvoiceType.GST,
                        invoice_date=today - timedelta(days=88 - n * 3 - (n % 2)),
                        status=SalesInvoice.Status.DRAFT, notes=note, created_by=owner,
                    )
                    lines = [
                        {
                            "product": product,
                            "quantity": Decimal(1 + (n + i) % 3),
                            "unit_price": product.selling_price,
                            "discount_percent": Decimal("5") if customer is local and i == 0 else Decimal("0"),
                            "gst_rate": product.gst_rate,
                        }
                        for i, product in enumerate(products[: 1 + n % len(products)])
                    ]
                    SalesService.set_items(invoice, lines, owner)
                if invoice.status == SalesInvoice.Status.DRAFT:
                    SalesService.complete(invoice, owner)
                    invoice.refresh_from_db()
                    made += 1
                # Older bills mostly paid, recent ones open: a real-looking outstanding and aging.
                share = Decimal("1") if n < 12 and n % 4 != 3 else (Decimal("0.5") if n % 4 == 1 else Decimal("0"))
                if share and invoice.grand_total > 0 and not PaymentAllocation.objects.filter(
                        company=company, sales_invoice=invoice).exists():
                    amount = (invoice.grand_total * share).quantize(Decimal("0.01"))
                    receipt = PaymentService.create_receipt(
                        company=company, customer=invoice.customer, amount=amount,
                        mode="UPI" if n % 2 else "CASH", receipt_date=invoice.invoice_date + timedelta(days=2),
                        notes=note, reference=f"DEMO-RCPT-{n:02d}", user=owner,
                    )
                    PaymentService.allocate_receipt(receipt=receipt, sales_invoice=invoice, amount=amount, user=owner)
                    paid += 1
            first = SalesInvoice.objects.filter(company=company, notes="DEMO:00").first()
            if first is not None and not SalesReturn.objects.filter(company=company, sales_invoice=first).exists():
                sales_return = SalesReturn.objects.create(
                    company=company, customer=first.customer, sales_invoice=first,
                    return_date=first.invoice_date + timedelta(days=5),
                    reason="Damaged strip returned by customer", created_by=owner,
                )
                item = first.items.select_related("product").first()
                ReturnService.set_return_items(sales_return, [{
                    "product": item.product, "quantity": Decimal("1"), "unit_price": item.unit_price,
                    "discount_percent": Decimal("0"), "gst_rate": item.gst_rate,
                }], owner)
                ReturnService.complete_return(sales_return, owner)
                returned = 1
        self.stdout.write(self.style.SUCCESS(
            f"Demo activity: {made} invoices completed, {paid} receipts, {returned} return "
            f"(already present items skipped)."
        ))
