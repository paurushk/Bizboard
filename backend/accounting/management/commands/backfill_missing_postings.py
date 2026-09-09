"""R-019: post missing JEs for completed notes / returns / BoE (chunked)."""

from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from accounts.models import Company
from accounting.models import JournalEntry
from accounting.services import PostingService, seed_chart_of_accounts
from core.exceptions import BusinessRuleError
from core.rls import rls_bypass
from inventory.models import MovementType, StockMovement
from purchases.models import BillOfEntry, PurchaseCreditNote, PurchaseDebitNote, PurchaseReturn
from sales.models import SalesReturn

CHUNK = 500


def _has_je(company, source_type, source_id, purpose=None) -> bool:
    # CR-103: empty POSTED headers are not "done" — PostingService would repair them.
    je = JournalEntry.objects.filter(
        company=company,
        source_type=source_type,
        source_id=source_id,
        status=JournalEntry.Status.POSTED,
        lines__isnull=False,
    )
    if purpose is not None:
        je = je.filter(purpose=purpose)
    return je.distinct().exists()


def _movement_cogs(company, movement_type, reference_type, reference_id) -> Decimal:
    return sum(
        (
            Decimal(str(movement.unit_cost or 0)) * abs(Decimal(str(movement.quantity or 0)))
            for movement in StockMovement.objects.filter(
                company=company,
                movement_type=movement_type,
                reference_type=reference_type,
                reference_id=str(reference_id),
            )
        ),
        Decimal("0"),
    )


def _chunked(qs, *, chunk_size=CHUNK):
    last_pk = 0
    qs = qs.order_by("pk")
    while True:
        batch = list(qs.filter(pk__gt=last_pk)[:chunk_size])
        if not batch:
            return
        last_pk = batch[-1].pk
        yield batch


class Command(BaseCommand):
    help = (
        "Post missing journals for COMPLETED purchase/sales notes, returns, and "
        "Bills of Entry. Skips VOID/CANCELLED. Use --dry-run first, then --company=N."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--company", type=int, help="Company id (required unless --dry-run).")

    def handle(self, *args, **options):
        dry_run = bool(options["dry_run"])
        company_id = options.get("company")
        if not dry_run and not company_id:
            raise CommandError("Pass --company=N to post, or --dry-run to scan.")

        with rls_bypass():
            companies = Company.objects.filter(accounting_enabled=True)
            if company_id:
                companies = companies.filter(pk=company_id)
            posted = 0
            skipped = 0
            would = 0
            for company in companies.iterator():
                seed_chart_of_accounts(company)
                p, s, w = self._backfill_company(company, dry_run=dry_run)
                posted += p
                skipped += s
                would += w
                self.stdout.write(
                    f"Company {company.id}: posted={p} skipped={s} would_post={w}"
                )
        if dry_run:
            self.stdout.write(self.style.WARNING(f"Dry-run: would post {would} ({skipped} skipped)."))
            return
        self.stdout.write(
            self.style.SUCCESS(f"Backfill completed; posted {posted} ({skipped} skipped).")
        )

    def _backfill_company(self, company, *, dry_run: bool) -> tuple[int, int, int]:
        posted = skipped = would = 0

        note_specs = (
            (PurchaseCreditNote, "PURCHASE_CREDIT_NOTE", "PURCHASE_CREDIT"),
            (PurchaseDebitNote, "PURCHASE_DEBIT_NOTE", "PURCHASE_DEBIT"),
        )
        for model, source_type, direction in note_specs:
            qs = model.objects.filter(company=company, status=model.Status.COMPLETED)
            for batch in _chunked(qs):
                for note in batch:
                    if note.status in ("VOID", "VOIDED", "CANCELLED"):
                        continue
                    if _has_je(company, source_type, note.id, "COMPLETE"):
                        continue
                    would += 1
                    if dry_run:
                        continue
                    try:
                        if PostingService.post_note(
                            note, source_type=source_type, direction=direction,
                        ):
                            posted += 1
                    except BusinessRuleError as exc:
                        skipped += 1
                        self.stderr.write(f"{source_type} {note.id}: {exc}")

        qs = PurchaseReturn.objects.filter(
            company=company, status=PurchaseReturn.Status.COMPLETED,
        )
        for batch in _chunked(qs):
            for pret in batch:
                if pret.status in ("VOID", "VOIDED", "CANCELLED"):
                    continue
                linked = PurchaseCreditNote.objects.filter(
                    purchase_return=pret,
                    status=PurchaseCreditNote.Status.COMPLETED,
                )
                for note in linked:
                    if _has_je(company, "PURCHASE_CREDIT_NOTE", note.id, "COMPLETE"):
                        continue
                    would += 1
                    if dry_run:
                        continue
                    try:
                        if PostingService.post_note(
                            note,
                            source_type="PURCHASE_CREDIT_NOTE",
                            direction="PURCHASE_CREDIT",
                        ):
                            posted += 1
                    except BusinessRuleError as exc:
                        skipped += 1
                        self.stderr.write(f"PR {pret.id} / PCN {note.id}: {exc}")

        qs = SalesReturn.objects.filter(company=company, status=SalesReturn.Status.COMPLETED)
        for batch in _chunked(qs):
            for sales_return in batch:
                if sales_return.status in ("VOID", "VOIDED", "CANCELLED"):
                    continue
                if _has_je(company, "SALES_RETURN", sales_return.id):
                    continue
                cogs = _movement_cogs(
                    company, MovementType.SALES_RETURN, "sales_return", sales_return.id,
                )
                if not cogs:
                    continue
                would += 1
                if dry_run:
                    continue
                try:
                    if PostingService.post_sales_return_cogs(sales_return, cogs):
                        posted += 1
                except BusinessRuleError as exc:
                    skipped += 1
                    self.stderr.write(f"SalesReturn {sales_return.id}: {exc}")

        qs = BillOfEntry.objects.filter(company=company, status=BillOfEntry.Status.COMPLETED)
        for batch in _chunked(qs):
            for boe in batch:
                if boe.status in ("VOID", "VOIDED", "CANCELLED"):
                    continue
                if _has_je(company, "BILL_OF_ENTRY", boe.id, "COMPLETE"):
                    continue
                would += 1
                if dry_run:
                    continue
                try:
                    if PostingService.post_bill_of_entry(boe):
                        posted += 1
                except BusinessRuleError as exc:
                    skipped += 1
                    self.stderr.write(f"BillOfEntry {boe.id}: {exc}")

        return posted, skipped, would
