"""P0-620: seed pilot UAT companies (C1–C5 profiles).

Usage:
  python manage.py seed_pilot_fixtures
  python manage.py seed_pilot_fixtures --perf-invoices 5000   # optional headroom seed on C1
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
from sales.models import SalesInvoice
from sales.services import SalesService


# GSTINs must match core.validators.GSTIN_RE (format-valid; not live-verified).
PROFILES = [
    {
        "code": "C1",
        "name": "Pilot Retail GST",
        "email": "pilot-c1@bizboard.local",
        "phone": "9000000001",
        "state": "Karnataka",
        "gstin": "29ABCDE1234F1ZW",
        "customer_state": "Karnataka",
        "rates": ("12", "18"),
    },
    {
        "code": "C2",
        "name": "Pilot Inter-State",
        "email": "pilot-c2@bizboard.local",
        "phone": "9000000002",
        "state": "Karnataka",
        "gstin": "29AABCU9603R1ZJ",
        "customer_state": "Maharashtra",
        "rates": ("18",),
    },
    {
        "code": "C3",
        "name": "Pilot Non-GST Shop",
        "email": "pilot-c3@bizboard.local",
        "phone": "9000000003",
        "state": "Karnataka",
        "gstin": "",
        "customer_state": "Karnataka",
        "rates": ("0",),
        "non_gst_company": True,
    },
    {
        "code": "C4",
        "name": "Pilot Multi-Rate",
        "email": "pilot-c4@bizboard.local",
        "phone": "9000000004",
        "state": "Karnataka",
        "gstin": "29AAACW3775F1Z2",
        "customer_state": "Karnataka",
        "rates": ("5", "28"),
    },
    {
        "code": "C5",
        "name": "Pilot Multi-User",
        "email": "pilot-c5@bizboard.local",
        "phone": "9000000005",
        "state": "Karnataka",
        "gstin": "29AAAAA0000A1ZY",
        "customer_state": "Karnataka",
        "rates": ("18",),
        "staff_email": "pilot-c5-staff@bizboard.local",
    },
]


class Command(BaseCommand):
    help = "Seed five pilot UAT company profiles (P0-620)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--perf-invoices",
            type=int,
            default=0,
            help=(
                "If >0, create this many completed invoices on C1 for perf floor seeding. "
                "Slow for large N (e.g. 5000); use only on staging."
            ),
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete previously seeded pilot-* companies before recreating.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        _env = getattr(settings, "DJANGO_ENV", "").strip().lower()
        # B6-016: never seed test data on a shared/real deployment.
        if _env in ("production", "staging") or not getattr(settings, "DEBUG", False):
            raise CommandError(
                "seed_pilot_fixtures refuses to run outside DEBUG / non-prod (DJANGO_ENV={}).".format(_env or "unset")
            )

        if options["reset"]:
            for p in PROFILES:
                Company.objects.filter(name=p["name"]).delete()
                User.objects.filter(email__iexact=p["email"]).delete()
                if p.get("staff_email"):
                    User.objects.filter(email__iexact=p["staff_email"]).delete()
            self.stdout.write("Reset previous pilot fixtures.")

        for profile in PROFILES:
            self._seed_profile(profile)

        n = options["perf_invoices"]
        if n > 0:
            self._seed_perf_invoices(n)

        self.stdout.write(self.style.SUCCESS(
            "Pilot fixtures ready. Password for all users: PilotPass123!\n"
            "Reset between UAT passes: python manage.py seed_pilot_fixtures --reset"
        ))

    def _seed_profile(self, profile):
        if Company.objects.filter(name=profile["name"]).exists():
            self.stdout.write(f"{profile['code']} {profile['name']} exists — skip.")
            return

        user = User.objects.create_user(
            email=profile["email"],
            password="PilotPass123!",
            full_name=f"{profile['code']} Owner",
            phone=profile["phone"],
        )
        company_kwargs = dict(
            name=profile["name"],
            legal_name=profile["name"],
            gstin=profile["gstin"],
            state=profile["state"],
            address="Pilot Street",
            city="Bengaluru",
            pincode="560001",
            tax_profile_confirmed_at=timezone.now(),
        )
        if profile.get("non_gst_company"):
            company_kwargs["registration_type"] = Company.RegistrationType.UNREGISTERED
        company = Company(**company_kwargs)
        company.full_clean()
        company.save()
        CompanyUser.objects.create(
            company=company, user=user, role=CompanyUser.Role.OWNER,
            can_manage_inventory=True, can_import=True,
            can_cancel_documents=True, can_view_financial_reports=True, can_export=True,
            can_create_sales=True, can_create_purchases=True, can_create_payments=True,
            can_post_journals=True,
        )
        if profile.get("staff_email"):
            staff = User.objects.create_user(
                email=profile["staff_email"],
                password="PilotPass123!",
                full_name=f"{profile['code']} Staff",
            )
            CompanyUser.objects.create(
                company=company, user=staff, role=CompanyUser.Role.SALES_STAFF,
                can_manage_inventory=False, can_import=False,
                can_cancel_documents=False, can_view_financial_reports=False, can_export=False,
            )

        unit = Unit.objects.create(company=company, name="Piece", short_name="pcs")
        customer = Customer.objects.create(
            company=company,
            name=f"{profile['code']} Customer",
            state=profile["customer_state"],
            phone="9876500001",
        )
        Supplier.objects.create(
            company=company, name=f"{profile['code']} Supplier", state=profile["state"],
        )
        for i, rate in enumerate(profile["rates"], start=1):
            product = Product.objects.create(
                company=company,
                name=f"{profile['code']} Widget {i}",
                sku=f"{profile['code']}-W{i}",
                hsn_code="8471" if rate != "0" else "",
                gst_rate=Decimal(rate),
                purchase_price=Decimal("80"),
                selling_price=Decimal("100"),
                mrp=Decimal("120"),
                unit=unit,
                reorder_level=Decimal("5"),
            )
            InventoryService.post_movement(
                company=company, product=product,
                movement_type=MovementType.OPENING_STOCK,
                quantity=Decimal("1000"),
                user=user,
            )
        self.stdout.write(f"Seeded {profile['code']} ({customer.name}).")

    def _seed_perf_invoices(self, count: int):
        company = Company.objects.filter(name="Pilot Retail GST").first()
        if not company:
            self.stdout.write("C1 missing — skip perf invoices.")
            return
        owner = CompanyUser.objects.filter(company=company, role=CompanyUser.Role.OWNER).first()
        customer = Customer.objects.filter(company=company).first()
        product = Product.objects.filter(company=company).first()
        if not owner or not customer or not product:
            return
        existing = SalesInvoice.objects.filter(company=company, status=SalesInvoice.Status.COMPLETED).count()
        to_create = max(0, count - existing)
        self.stdout.write(f"Creating {to_create} perf invoices on C1 (have {existing})...")
        today = timezone.localdate()
        for i in range(to_create):
            inv = SalesInvoice.objects.create(
                company=company,
                customer=customer,
                invoice_type=SalesInvoice.InvoiceType.GST,
                invoice_date=today,
                status=SalesInvoice.Status.DRAFT,
                created_by=owner.user,
            )
            SalesService.set_items(
                inv,
                [{
                    "product": product,
                    "quantity": Decimal("1"),
                    "unit_price": Decimal("100"),
                    "discount_percent": Decimal("0"),
                    "gst_rate": product.gst_rate,
                }],
                owner.user,
            )
            SalesService.complete(inv, owner.user)
            if (i + 1) % 500 == 0:
                self.stdout.write(f"  …{i + 1}/{to_create}")
