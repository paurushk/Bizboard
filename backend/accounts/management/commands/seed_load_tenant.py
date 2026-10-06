"""Staging/test load fixture. Not a substitute for seed_synthetic_bulk.

``seed_synthetic_bulk`` refuses staging, attaches every row to one customer
and one product, and bulk-inserts COMPLETED invoices. This command is the
opposite: it runs only when DJANGO_ENV is staging or test, refuses
production, and creates invoices through SalesService.complete.

    python manage.py seed_load_tenant --invoices 50000 --password "$SEED_LOAD_PASSWORD"
    python manage.py seed_load_tenant --invoices 50000 --shard 0/4 --password ...

Side effects suppressed while the command runs (see core.seed_guard):
PDF enqueue, and the credit-note / debit-note / challan PDF handlers.
GSP submit is not called by Complete. Re-runs skip invoices whose notes
already hold SEED_LOAD:{index}.

Mix over each block of 20 invoices: 14 small B2C (70%), 5 multi-line B2B
(25%), 1 sales return of a one-line invoice (5%). About 60% of non-return
invoices get a cash receipt (half of those are partial).

``--bulk-fallback`` is rejected. A COMPLETED row without lines, stock, and
ledger entries fails ``check_invariants``. Parallelise with ``--shard i/n``
instead of inserting rows.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import Company, CompanyUser, User
from core.seed_guard import seed_load_scope
from inventory.models import MovementType
from inventory.services import InventoryService
from masters.models import Customer, Product, Unit
from payments.models import CustomerReceipt, PaymentAllocation
from payments.services import PaymentService
from sales.models import SalesInvoice, SalesReturn
from sales.return_service import ReturnService
from sales.services import SalesService

LOAD_COMPANY = "Load Tenant"
LOAD_EMAIL = "load-tenant@bizboard.local"


def mix_bucket(index: int) -> str:
    """14/20 b2c, 5/20 b2b, 1/20 return."""
    slot = index % 20
    if slot == 19:
        return "return"
    if slot >= 14:
        return "b2b"
    return "b2c"


def _parse_shard(raw: str) -> tuple[int, int]:
    parts = (raw or "0/1").split("/")
    if len(parts) != 2:
        raise CommandError("--shard must look like 0/4")
    index, count = int(parts[0]), int(parts[1])
    if count < 1 or index < 0 or index >= count:
        raise CommandError("--shard index must be inside 0..count-1")
    return index, count


class Command(BaseCommand):
    help = "Create a realistic completed-invoice tenant for staging load tests."

    def add_arguments(self, parser):
        parser.add_argument("--invoices", type=int, default=50000)
        parser.add_argument("--products", type=int, default=1000)
        parser.add_argument("--customers", type=int, default=500)
        parser.add_argument("--company", default=LOAD_COMPANY)
        parser.add_argument("--password", required=True)
        parser.add_argument("--shard", default="0/1")
        parser.add_argument(
            "--bulk-fallback",
            action="store_true",
            help="Rejected. Bulk-inserted COMPLETED rows fail check_invariants.",
        )

    def handle(self, *args, **options):
        env = getattr(settings, "DJANGO_ENV", "").strip().lower()
        if env == "production" or env not in {"staging", "test"}:
            raise CommandError(
                f"seed_load_tenant refuses to run unless DJANGO_ENV is staging or test "
                f"(DJANGO_ENV={env or 'unset'})."
            )
        if options["bulk_fallback"]:
            raise CommandError(
                "Refusing --bulk-fallback. A COMPLETED row written without lines, stock, "
                "and ledger entries fails check_invariants, so it is not a valid load fixture. "
                "Use --shard i/n to parallelise SalesService.complete instead."
            )
        invoices = max(1, options["invoices"])
        n_products = max(1, options["products"])
        n_customers = max(1, options["customers"])
        shard_index, shard_count = _parse_shard(options["shard"])
        with seed_load_scope():
            company, user = self._ensure_company(
                options["company"], options["password"], n_products, n_customers, invoices
            )
            products = list(Product.objects.filter(company=company).order_by("id"))
            customers = list(Customer.objects.filter(company=company).order_by("id"))
            if len(products) < n_products or len(customers) < n_customers:
                raise CommandError("Load tenant masters are short. Delete the company and re-run.")
            done = 0
            for index in range(invoices):
                if index % shard_count != shard_index:
                    continue
                note = f"SEED_LOAD:{index:06d}"
                before = SalesInvoice.objects.filter(company=company, notes=note).count()
                self._service_one(
                    company, user, customers[index % n_customers], products, n_products, index, note
                )
                if SalesInvoice.objects.filter(company=company, notes=note).count() == before and before:
                    continue
                done += 1
                if done % 100 == 0:
                    self.stderr.write(f"  ...{done} created on shard {shard_index}/{shard_count}")
            seeded = SalesInvoice.objects.filter(company=company, notes__startswith="SEED_LOAD:")
            completed = seeded.filter(status=SalesInvoice.Status.COMPLETED).count()
            returned = seeded.filter(status=SalesInvoice.Status.RETURNED).count()
            self.stdout.write(
                f"company_id={company.id} email={user.email} "
                f"completed={completed} returned={returned} created_this_run={done}"
            )

    def _ensure_company(self, name, password, n_products, n_customers, invoices):
        company = Company.objects.filter(name=name).first()
        if company is None:
            user = User.objects.filter(email=LOAD_EMAIL).first()
            if user is None:
                user = User.objects.create_user(
                    email=LOAD_EMAIL,
                    password=password,
                    full_name="Load Tenant Owner",
                    phone="9000000099",
                )
            else:
                user.set_password(password)
                user.save(update_fields=["password"])
            company = Company.objects.create(
                name=name,
                legal_name=f"{name} Pvt Ltd",
                gstin="29AABCU9603R1ZJ",
                state="Karnataka",
                address="1 Load Street",
                city="Bengaluru",
                pincode="560001",
                phone="08040000000",
                email="billing@load-tenant.local",
                assume_local_state_for_blank_party=True,
                negative_stock_policy=Company.NegativeStockPolicy.BLOCK,
                tax_profile_confirmed_at=timezone.now(),
                billing_override_active=True,
                feature_flags={"ENABLE_GSTR": True},
            )
            CompanyUser.objects.create(
                company=company,
                user=user,
                role=CompanyUser.Role.OWNER,
                can_manage_inventory=True,
                can_import=True,
                can_cancel_documents=True,
                can_view_financial_reports=True,
                can_export=True,
                can_create_sales=True,
                can_create_purchases=True,
                can_create_payments=True,
                can_post_journals=True,
            )
        else:
            user = CompanyUser.objects.filter(company=company, role=CompanyUser.Role.OWNER).order_by("id").first()
            if user is None:
                raise CommandError(f"{name} has no owner.")
            user = user.user
            user.set_password(password)
            user.save(update_fields=["password"])
            if not company.billing_override_active or not (company.feature_flags or {}).get("ENABLE_GSTR"):
                company.billing_override_active = True
                flags = dict(company.feature_flags or {})
                flags["ENABLE_GSTR"] = True
                company.feature_flags = flags
                company.save(update_fields=["billing_override_active", "feature_flags"])

        unit = Unit.objects.filter(company=company, short_name="pcs").first()
        if unit is None:
            unit = Unit.objects.create(company=company, name="Piece", short_name="pcs")
        existing_products = Product.objects.filter(company=company).count()
        if existing_products < n_products:
            Product.objects.bulk_create(
                [
                    Product(
                        company=company,
                        name=f"Load product {i}",
                        sku=f"LOAD-{i:05d}",
                        hsn_code="8471",
                        gst_rate=Decimal("0"),
                        purchase_price=Decimal("50"),
                        selling_price=Decimal("80"),
                        mrp=Decimal("100"),
                        unit=unit,
                    )
                    for i in range(existing_products, n_products)
                ],
                ignore_conflicts=True,
            )
        existing_customers = Customer.objects.filter(company=company).count()
        if existing_customers < n_customers:
            Customer.objects.bulk_create(
                [
                    Customer(
                        company=company,
                        name=f"Load customer {i}",
                        state="Karnataka",
                        phone=f"98{i:08d}"[:10],
                    )
                    for i in range(existing_customers, n_customers)
                ]
            )
        needed = Decimal((invoices // max(n_products, 1)) * 20 + 100)
        for product in Product.objects.filter(company=company, sku__startswith="LOAD-"):
            available = InventoryService.available_quantity(company, product)
            short = needed - available
            if short > 0:
                InventoryService.post_movement(
                    company=company,
                    product=product,
                    movement_type=MovementType.PURCHASE,
                    quantity=short,
                    unit_cost=product.purchase_price,
                    user=user,
                    reference_type="seed_load_tenant",
                    reason="Load fixture stock",
                )
        return company, user

    def _line(self, product):
        return {
            "product": product,
            "quantity": Decimal("1"),
            "unit_price": product.selling_price,
            "discount_percent": Decimal("0"),
            "gst_rate": Decimal("0"),
        }

    def _service_one(self, company, user, customer, products, n_products, index, note):
        bucket = mix_bucket(index)
        line_count = 5 + (index % 11) if bucket == "b2b" else 1
        day = timezone.localdate() - timedelta(days=int(index % 360))
        invoice = SalesInvoice.objects.filter(company=company, notes=note).first()
        if invoice is not None and invoice.status == SalesInvoice.Status.RETURNED:
            return
        if invoice is None:
            invoice = SalesInvoice.objects.create(
                company=company,
                customer=customer,
                invoice_type=SalesInvoice.InvoiceType.NON_GST,
                invoice_date=day,
                status=SalesInvoice.Status.DRAFT,
                notes=note,
                created_by=user,
            )
        if invoice.status == SalesInvoice.Status.DRAFT:
            if not invoice.items.exists():
                SalesService.set_items(
                    invoice,
                    [self._line(products[(index + offset) % n_products]) for offset in range(line_count)],
                    user,
                )
            SalesService.complete(invoice, user)
            invoice.refresh_from_db()
        if invoice.status == SalesInvoice.Status.COMPLETED and bucket != "return":
            self._ensure_receipt(company, user, customer, invoice, index, note)
        if bucket == "return" and invoice.status == SalesInvoice.Status.COMPLETED:
            self._ensure_return(company, user, customer, invoice)

    def _ensure_receipt(self, company, user, customer, invoice, index, note):
        if (index % 5) >= 3 or invoice.grand_total <= 0:
            return
        if PaymentAllocation.objects.filter(company=company, sales_invoice=invoice).exists():
            return
        amount = invoice.grand_total if index % 2 == 0 else (invoice.grand_total / 2).quantize(Decimal("0.01"))
        if amount <= 0:
            return
        receipt = CustomerReceipt.objects.filter(company=company, notes=note).first()
        if receipt is None:
            receipt = PaymentService.create_receipt(
                company=company,
                customer=customer,
                amount=amount,
                mode="CASH",
                receipt_date=invoice.invoice_date,
                notes=note,
                reference=f"SEED-{index}",
                user=user,
            )
        PaymentService.allocate_receipt(
            receipt=receipt, sales_invoice=invoice, amount=min(amount, receipt.amount), user=user
        )

    def _ensure_return(self, company, user, customer, invoice):
        sales_return = SalesReturn.objects.filter(company=company, sales_invoice=invoice).first()
        if sales_return is not None and sales_return.status == SalesReturn.Status.COMPLETED:
            return
        if sales_return is None:
            sales_return = SalesReturn.objects.create(
                company=company,
                customer=customer,
                sales_invoice=invoice,
                return_date=invoice.invoice_date,
                reason="Load fixture return",
                created_by=user,
            )
        if not sales_return.items.exists():
            item = invoice.items.select_related("product").first()
            ReturnService.set_return_items(sales_return, [self._line(item.product)], user)
        ReturnService.complete_return(sales_return, user)

