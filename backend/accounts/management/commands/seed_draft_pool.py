"""QOS-0003 — pre-create a pool of real, completable DRAFT sales invoices.

load/k6_slo.js's Complete scenario used to hammer POST .../complete/ on a
single pre-created draft: only the first call could actually complete it,
every later call correctly got "400 already completed" in ~70-200ms, so the
measured p95 was conflict-rejection latency, not real Complete work (see
docs/roadmap/ticket-logs/X-01.md, 2026-09-12). This command gives k6 a large
enough pool of distinct drafts to complete one per iteration instead.

    python manage.py seed_draft_pool --count 700

Prints only the created invoice IDs, comma-separated, on stdout (progress
goes to stderr) so it can be piped straight into k6:

    export DRAFT_INVOICE_IDS=$(python manage.py seed_draft_pool --count 700)
    k6 run -e DRAFT_INVOICE_IDS=$DRAFT_INVOICE_IDS -e BASE_URL=... \\
        -e EMAIL=... -e PASSWORD=... load/k6_slo.js

Size the pool above the run's expected total iteration count for the
"complete" scenario (VUs * duration / ~1s per iteration) — once the pool is
exhausted k6_slo.js stops calling the endpoint rather than silently falling
back to re-completing a draft.

Requires `seed_demo` to have already created "Demo Traders" (same
precondition as seed_synthetic_bulk, meant to run alongside it so the
50k-tenant soak has both COMPLETED history and a fresh DRAFT pool). If the
target company has an active billing plan with a monthly_complete_limit,
raise or clear it first — Complete is now quota-checked and a tight limit
will surface as real rejections partway through the run.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import Company, CompanyUser
from inventory.models import MovementType
from inventory.services import InventoryService
from masters.models import Customer, Product
from sales.models import SalesInvoice
from sales.services import SalesService


class Command(BaseCommand):
    help = "Pre-create a pool of real DRAFT sales invoices for load/k6_slo.js's Complete scenario."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=700)

    def handle(self, *args, **options):
        _env = getattr(settings, "DJANGO_ENV", "").strip().lower()
        if _env == "production" or not getattr(settings, "DEBUG", False):
            raise CommandError(
                f"seed_draft_pool refuses to run outside DEBUG / non-production (DJANGO_ENV={_env or 'unset'})."
            )

        company = Company.objects.filter(name="Demo Traders").first()
        if not company:
            raise CommandError("Run `seed_demo` first — seed_draft_pool builds on its company/customer/product.")
        customer = Customer.objects.filter(company=company).first()
        product = Product.objects.filter(company=company).first()
        owner = CompanyUser.objects.filter(company=company).order_by("id").first()
        if not customer or not product or not owner:
            raise CommandError("Demo Traders is missing a customer/product/user to attach draft invoices to.")

        count = max(1, options["count"])
        # seed_demo only opens 100 units of stock — nowhere near enough for a
        # load-test-sized pool that each completes 1 unit.
        InventoryService.post_movement(
            company=company, product=product,
            movement_type=MovementType.OPENING_STOCK,
            quantity=Decimal(count), unit_cost=product.purchase_price, user=owner.user,
        )

        today = timezone.localdate()
        ids: list[str] = []
        for i in range(count):
            invoice = SalesInvoice.objects.create(
                company=company,
                customer=customer,
                invoice_type=SalesInvoice.InvoiceType.NON_GST,
                invoice_date=today,
                status=SalesInvoice.Status.DRAFT,
                created_by=owner.user,
            )
            SalesService.set_items(
                invoice,
                [{
                    "product": product,
                    "quantity": Decimal("1"),
                    "unit_price": Decimal("100"),
                    "discount_percent": Decimal("0"),
                    "gst_rate": Decimal("0"),
                }],
                owner.user,
            )
            ids.append(str(invoice.id))
            if (i + 1) % 500 == 0:
                self.stderr.write(f"  ...{i + 1}/{count}")

        self.stderr.write(self.style.SUCCESS(f"Seeded {count} DRAFT invoices on {company.name} ({company.id})."))
        self.stdout.write(",".join(ids))
