"""SR-50 — Seed the H-05 CA-review demo company and emit the review packet.

Builds one ARCH-03 (semi-wholesaler) company with ~1 month (Aug 2026) of the
complete B2B trade loop:

  opening stock -> purchase bills (stock + AP, atomic) -> multi-rate B2B sales
  invoices (incl. one inter-state IGST and one 206C TCS invoice) -> customer
  receipts with full + partial allocations -> month-end soft-close.

Then writes the CA-review packet to ``<repo>/build/h05_packet/``:
GSTR-1 + GSTR-3B worksheets, trial balance, P&L, balance sheet (JSON) and a
readable ``SUMMARY.md``. Asserts the trial balance nets to zero and the
whole-chain invariants hold.

Usage:
  python manage.py seed_h05_demo            # create (idempotent: skips if present)
  python manage.py seed_h05_demo --reset    # delete + rebuild
  python manage.py seed_h05_demo --packet-only   # just regenerate the packet

Set ``CELERY_TASK_ALWAYS_EAGER=1`` to silence the harmless "connect to redis"
retry noise when no broker is running locally (``safe_delay`` swallows it either
way). Refuses to run outside DEBUG / non-prod (mirrors seed_pilot_fixtures).

Tracker: docs/roadmap/SCOPE_REVISION_2026-09-09b_IMPLEMENTATION_PLAN.md  (SR-50)
Known v1 gap: opening party balances and the sales credit note / purchase debit
note (CDNR coverage) are deferred to SR-50 v2.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import Company, CompanyUser, User
from inventory.models import MovementType
from inventory.services import InventoryService
from masters.models import Customer, Product, Supplier, Unit
from payments.services import PaymentService
from purchases.models import PurchaseInvoice
from purchases.services import PurchaseService
from sales.models import SalesInvoice
from sales.services import SalesService

COMPANY_NAME = "H05 Demo Wholesale"
OWNER_EMAIL = "h05-owner@bizboard.local"
OWNER_PASSWORD = "PilotPass123!"
PERIOD = "2026-08"
MONTH_START = date(2026, 8, 1)
MONTH_END = date(2026, 8, 31)

# format-valid GSTINs (core.validators.GSTIN_RE); not live-verified
COMPANY_GSTIN = "29ABCDE1234F1ZW"        # Karnataka
CUST_KA_1_GSTIN = "29AAAAA0000A1ZY"
CUST_KA_2_GSTIN = "29AAACW3775F1Z2"
CUST_MH_GSTIN = "27AABCU9603R1ZX"        # Maharashtra -> IGST
SUPPLIER_GSTIN = "29AABCU9603R1ZJ"


class Command(BaseCommand):
    help = "Seed the H-05 CA-review demo company and emit the review packet (SR-50)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete and rebuild the demo company.")
        parser.add_argument("--packet-only", action="store_true", help="Only regenerate the packet from existing data.")

    def handle(self, *args, **options):
        env = getattr(settings, "DJANGO_ENV", "").strip().lower()
        if env in ("production", "staging") or not getattr(settings, "DEBUG", False):
            raise CommandError(
                f"seed_h05_demo refuses to run outside DEBUG / non-prod (DJANGO_ENV={env or 'unset'})."
            )

        if options["packet_only"]:
            company = Company.objects.filter(name=COMPANY_NAME).first()
            if not company:
                raise CommandError("No H05 demo company — run without --packet-only first.")
            self._emit_packet(company)
            return

        if options["reset"]:
            self._teardown()
            self.stdout.write("Reset previous H05 demo.")

        if Company.objects.filter(name=COMPANY_NAME).exists():
            self.stdout.write(f"{COMPANY_NAME} exists — regenerating packet only. Use --reset to rebuild.")
            self._emit_packet(Company.objects.get(name=COMPANY_NAME))
            return

        with transaction.atomic():
            company, owner, ctx = self._build_company()
            self._run_month(company, owner, ctx)
            self._close_period(company, owner)

        self._emit_packet(company)

    def _teardown(self):
        """Delete a prior H05 demo. Company FKs are mostly PROTECT, so clear the
        business rows via the tenant-wipe helper, then the append-only event
        tables, then the company + owner."""
        company = Company.objects.filter(name=COMPANY_NAME).first()
        if company:
            from accounts.tenant_backup import wipe_logical_tenant_rows
            from core.models import AuditEvent, MoneyFieldAudit, StatutoryDocumentEvent

            with transaction.atomic():
                wipe_logical_tenant_rows(company)
                MoneyFieldAudit.objects.filter(company=company).delete()
                StatutoryDocumentEvent.objects.filter(company=company).delete()
                AuditEvent.objects.filter(company=company).delete()
                for rel in ("gst_return_periods", "gst_return_snapshots"):
                    mgr = getattr(company, rel, None)
                    if mgr is not None:
                        mgr.all().delete()
                company.delete()
        User.objects.filter(email__iexact=OWNER_EMAIL).delete()

    # ------------------------------------------------------------------ build

    def _build_company(self):
        owner = User.objects.create_user(
            email=OWNER_EMAIL, password=OWNER_PASSWORD,
            full_name="H05 Owner", phone="9000000050",
        )
        company = Company(
            name=COMPANY_NAME, legal_name=COMPANY_NAME, gstin=COMPANY_GSTIN,
            state="Karnataka", address="Wholesale Market Road", city="Bengaluru",
            pincode="560002", registration_type=Company.RegistrationType.REGULAR,
            tax_profile_confirmed_at=timezone.now(),
        )
        company.full_clean()
        company.save()
        company.accounting_enabled = True
        company.save(update_fields=["accounting_enabled"])

        CompanyUser.objects.create(
            company=company, user=owner, role=CompanyUser.Role.OWNER,
            can_manage_inventory=True, can_import=True, can_cancel_documents=True,
            can_view_financial_reports=True, can_export=True, can_create_sales=True,
            can_create_purchases=True, can_create_payments=True, can_post_journals=True,
        )

        unit = Unit.objects.create(company=company, name="Piece", short_name="pcs")

        # Building-supplies trader: the slabs in force on the document date
        # (post 22-Sep-2025 rationalisation) for this trade are 5% and 18%.
        # HSNs 2505 / 2523 / 7318 are not in the starter HSN catalog, so the
        # product-master rate stands; 8536 resolves to 18% from the catalog.
        # (name, sku, hsn, product_gst_rate, purchase_cost, selling_price)
        specs = [
            ("M-Sand (per ton)", "SAND-T", "2505", "5", "900", "1150"),
            ("OPC 43 Cement 50kg", "CEM-50", "2523", "18", "360", "430"),
            ("MS Fastener Bolt M12", "BOLT-12", "7318", "18", "9", "14"),
            ("MCB 32A DP", "MCB-32", "8536", "18", "210", "320"),
        ]
        products = []
        for name, sku, hsn, rate, cost, sell in specs:
            p = Product.objects.create(
                company=company, name=name, sku=sku, hsn_code=hsn,
                gst_rate=Decimal(rate), purchase_price=Decimal(cost),
                selling_price=Decimal(sell), mrp=Decimal(sell) + Decimal("40"),
                unit=unit, reorder_level=Decimal("20"),
            )
            InventoryService.post_movement(
                company=company, product=p, movement_type=MovementType.OPENING_STOCK,
                quantity=Decimal("500"), user=owner,
            )
            products.append(p)

        customers = {
            "ka1": Customer.objects.create(company=company, name="Sri Balaji Traders",
                                           state="Karnataka", gstin=CUST_KA_1_GSTIN, phone="9876500001"),
            "ka2": Customer.objects.create(company=company, name="Anand Electricals",
                                           state="Karnataka", gstin=CUST_KA_2_GSTIN, phone="9876500002"),
            "mh": Customer.objects.create(company=company, name="Deccan Hardware LLP",
                                          state="Maharashtra", gstin=CUST_MH_GSTIN, phone="9876500003"),
        }
        supplier = Supplier.objects.create(
            company=company, name="Metro Wholesale Supply", state="Karnataka", gstin=SUPPLIER_GSTIN,
        )

        self.stdout.write(f"Built {COMPANY_NAME}: 4 products, 3 customers, 1 supplier, opening stock 500 ea.")
        return company, owner, {"products": products, "customers": customers, "supplier": supplier, "unit": unit}

    # -------------------------------------------------------------- activity

    def _purchase(self, company, owner, supplier, when, bill_no, lines):
        pi = PurchaseInvoice.objects.create(
            company=company, supplier=supplier,
            purchase_type=PurchaseInvoice.PurchaseType.GST,
            invoice_date=when, supplier_bill_number=bill_no,
            status=PurchaseInvoice.Status.DRAFT, created_by=owner,
        )
        PurchaseService.set_items(pi, lines, owner)
        PurchaseService.complete(pi, owner, confirm_no_rcm=True)
        return pi

    def _sale(self, company, owner, customer, when, lines, *, tcs_rate=None):
        si = SalesInvoice.objects.create(
            company=company, customer=customer,
            invoice_type=SalesInvoice.InvoiceType.GST,
            invoice_date=when, status=SalesInvoice.Status.DRAFT, created_by=owner,
        )
        SalesService.set_items(si, lines, owner)
        if tcs_rate is not None:
            si.tcs_rate = Decimal(str(tcs_rate))
            si.save(update_fields=["tcs_rate"])
        SalesService.complete(si, owner)
        si.refresh_from_db()
        return si

    def _receipt(self, company, owner, customer, when, amount, utr):
        return PaymentService.create_receipt(
            company=company, customer=customer, amount=Decimal(str(amount)),
            mode="BANK", receipt_date=when, utr=utr, user=owner,
        )

    def _run_month(self, company, owner, ctx):
        P = ctx["products"]
        C = ctx["customers"]
        sup = ctx["supplier"]

        def pl(prod, qty, price):
            return {"product": prod, "quantity": Decimal(str(qty)),
                    "unit_price": Decimal(str(price)), "gst_rate": prod.gst_rate}

        def sl(prod, qty, price, disc="0"):
            return {"product": prod, "quantity": Decimal(str(qty)),
                    "unit_price": Decimal(str(price)), "discount_percent": Decimal(disc),
                    "gst_rate": prod.gst_rate}

        # P[0] M-Sand/ton 5% | P[1] Cement bag 18% | P[2] MS Bolt 18% | P[3] MCB 18%
        # --- inward: 3 purchase bills across the month ---
        self._purchase(company, owner, sup, date(2026, 8, 2), "MW/2026/1187",
                       [pl(P[0], 400, "880"), pl(P[3], 200, "205")])
        self._purchase(company, owner, sup, date(2026, 8, 11), "MW/2026/1231",
                       [pl(P[1], 600, "355"), pl(P[2], 5000, "8.50")])
        self._purchase(company, owner, sup, date(2026, 8, 21), "MW/2026/1290",
                       [pl(P[3], 150, "208"), pl(P[0], 250, "890")])
        self.stdout.write("  inward: 3 purchase bills completed (stock + AP).")

        # --- outward: B2B sales, 5% + 18% mix, two inter-state, one with TCS ---
        inv = []
        inv.append(self._sale(company, owner, C["ka1"], date(2026, 8, 3),
                              [sl(P[0], 60, "1150"), sl(P[3], 20, "320", "2")]))     # 5% + 18%
        inv.append(self._sale(company, owner, C["ka2"], date(2026, 8, 6),
                              [sl(P[1], 120, "430"), sl(P[2], 800, "14")]))          # 18%
        inv.append(self._sale(company, owner, C["mh"], date(2026, 8, 9),
                              [sl(P[3], 80, "315"), sl(P[1], 100, "425")]))          # IGST 18%
        inv.append(self._sale(company, owner, C["ka1"], date(2026, 8, 14),
                              [sl(P[0], 90, "1140"), sl(P[1], 60, "428")]))          # 5% + 18%
        inv.append(self._sale(company, owner, C["ka2"], date(2026, 8, 18),
                              [sl(P[3], 40, "322"), sl(P[2], 1200, "13.50")]))       # 18%
        inv.append(self._sale(company, owner, C["ka1"], date(2026, 8, 24),
                              [sl(P[0], 45, "1145"), sl(P[3], 35, "320")],
                              tcs_rate="0.1"))                                       # 5% + 18% + 206C(1H)
        inv.append(self._sale(company, owner, C["mh"], date(2026, 8, 27),
                              [sl(P[1], 150, "424"), sl(P[0], 80, "1148")]))         # IGST 18% + 5%
        self.stdout.write(f"  outward: {len(inv)} B2B invoices (2 inter-state IGST, 1 with 206C TCS).")

        # --- receipts: full + partial allocations ---
        r1 = self._receipt(company, owner, C["ka1"], date(2026, 8, 12), inv[0].grand_total, "UTR8120001")
        PaymentService.allocate_receipt(receipt=r1, sales_invoice=inv[0], amount=inv[0].grand_total, user=owner)

        r2 = self._receipt(company, owner, C["ka2"], date(2026, 8, 20), inv[1].grand_total, "UTR8120002")
        PaymentService.allocate_receipt(receipt=r2, sales_invoice=inv[1], amount=inv[1].grand_total, user=owner)

        # partial: pay half of the inter-state invoice
        half = (inv[2].grand_total / 2).quantize(Decimal("0.01"))
        r3 = self._receipt(company, owner, C["mh"], date(2026, 8, 25), half, "UTR8120003")
        PaymentService.allocate_receipt(receipt=r3, sales_invoice=inv[2], amount=half, user=owner)

        r4 = self._receipt(company, owner, C["ka1"], date(2026, 8, 28), inv[3].grand_total, "UTR8120004")
        PaymentService.allocate_receipt(receipt=r4, sales_invoice=inv[3], amount=inv[3].grand_total, user=owner)
        self.stdout.write("  receipts: 4 posted; 3 full + 1 partial allocation (rest is open AR).")

        self._ctx_invoices = inv

    def _close_period(self, company, owner):
        try:
            from reporting.gst_periods import soft_close_period
            soft_close_period(company, PERIOD, owner)
            self.stdout.write(f"  period {PERIOD} soft-closed.")
        except Exception as exc:  # noqa: BLE001 — packet still useful if close is unavailable
            self.stdout.write(self.style.WARNING(f"  period close skipped: {exc}"))

    # ------------------------------------------------------------------ packet

    def _emit_packet(self, company):
        out_dir = settings.BASE_DIR.parent / "build" / "h05_packet"
        out_dir.mkdir(parents=True, exist_ok=True)

        from accounting.reports import balance_sheet, profit_and_loss, trial_balance
        from reporting.gst_returns import build_gstr1, build_gstr3b

        tb = trial_balance(company, as_of=MONTH_END)
        pnl = profit_and_loss(company, date_from=MONTH_START, date_to=MONTH_END)
        bs = balance_sheet(company, as_of=MONTH_END)
        g1 = build_gstr1(company, PERIOD)
        g3b = build_gstr3b(company, PERIOD, gstr1=g1)

        artefacts = {
            "trial_balance": tb, "profit_and_loss": pnl, "balance_sheet": bs,
            "gstr1": g1, "gstr3b": g3b,
        }
        for name, payload in artefacts.items():
            (out_dir / f"{name}_{PERIOD}.json").write_text(
                json.dumps(payload, indent=2, default=str, sort_keys=True), encoding="utf-8"
            )

        dr, cr = _tb_totals(tb)
        balanced = dr == cr
        (out_dir / "SUMMARY.md").write_text(_summary_md(company, tb, dr, cr, balanced), encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(f"Packet written to {out_dir}"))
        self.stdout.write(f"  Trial balance: debit {dr}  credit {cr}  balanced={balanced}")

        if not balanced:
            raise CommandError(f"Trial balance does not net to zero (Dr {dr} != Cr {cr}).")

        try:
            from core.invariants import assert_all_invariants
            assert_all_invariants(company)
            self.stdout.write(self.style.SUCCESS("  Whole-chain invariants: OK"))
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"Invariant check failed: {exc}")


def _tb_totals(tb):
    """Sum debit / credit columns from whatever shape trial_balance returns."""
    rows = tb.get("rows") if isinstance(tb, dict) else tb
    if isinstance(tb, dict) and "totals" in tb and isinstance(tb["totals"], dict):
        t = tb["totals"]
        return (
            Decimal(str(t.get("debit", t.get("total_debit", 0)) or 0)),
            Decimal(str(t.get("credit", t.get("total_credit", 0)) or 0)),
        )
    dr = cr = Decimal("0")
    for row in rows or []:
        dr += Decimal(str(row.get("debit", 0) or 0))
        cr += Decimal(str(row.get("credit", 0) or 0))
    return dr.quantize(Decimal("0.01")), cr.quantize(Decimal("0.01"))


def _summary_md(company, tb, dr, cr, balanced):
    return f"""# H-05 CA Review Packet — {company.name}

**Period:** {PERIOD} (01–31 Aug 2026)  ·  **GSTIN:** {company.gstin}  ·  **Basis:** accrual, accounting books ON

Trade: building-supplies wholesaler. GST slabs in force on the document date (post
22-Sep-2025 rationalisation) for this trade: **5%** (natural sand) and **18%**
(cement, fasteners, MCBs). Several invoices carry both rates.

## What is in this packet

| File | What it is |
|---|---|
| `gstr1_{PERIOD}.json` | GSTR-1 outward-supply worksheet (B2B, incl. 2 inter-state IGST invoices) |
| `gstr3b_{PERIOD}.json` | GSTR-3B liability / ITC worksheet, built from the same period data |
| `trial_balance_{PERIOD}.json` | Trial balance as of 31 Aug 2026 |
| `profit_and_loss_{PERIOD}.json` | P&L for the period |
| `balance_sheet_{PERIOD}.json` | Balance sheet as of 31 Aug 2026 |

## The ask (hypothesis H-05)

> Could you file this client's monthly GSTR-1 and GSTR-3B **directly from these worksheets**,
> without re-deriving the tax splits or the ledgers in your own software?

Please note specifically:
- Do the GSTR-1 tax splits (CGST/SGST vs IGST) match your expectation for the invoices listed?
- Does GSTR-3B 3.1(a) outward liability tie to the GSTR-1 totals?
- ITC: this build reports **books ITC as provisional** in 3B Table 4 until a GSTR-2B is
  uploaded and matched — the 3 purchase bills' ITC is in the ledgers but shown provisional.
  Is that treatment acceptable, or do you need the 2B-matched figure in the worksheet?
- Trial balance: **Dr {dr} / Cr {cr} — balanced: {balanced}**. Does it foot for you?
- Is the 206C TCS invoice (24 Aug) presented in a way you can reconcile?

## Known scope (pilot)

Offline worksheets only — no live GSP portal filing, no live IRN/e-way. Composition, RCM,
fixed assets, TDS/TCS **returns**, and import/BoE landed cost are out of pilot scope
(`FREEZE_SCOPE.md` → Scope revision 2026-09-09b). Opening party balances and CDNR credit/debit
notes are not in this v1 packet (SR-50 v2).
"""
