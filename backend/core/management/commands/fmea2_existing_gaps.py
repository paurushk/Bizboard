"""List, and optionally repair, rows the FMEA fixes do not rewrite by themselves.

Campaign ROI is computed in crm.campaigns._won_revenue on each read. There is
no stored campaign revenue to backfill.

--apply writes one labeled audit row for a completed document that has none.
It does not pretend the row was written at completion time. For a complaint
that points at both a return and a credit note, it keeps the return and clears
the credit-note pointer only when that note already belongs to the return or
is already cancelled. It does not cancel a credit note and does not drop a
separate draft.
"""

from django.core.management.base import BaseCommand
from django.db.models import Q

from complaints.models import Complaint
from core.models import AuditEvent
from core.rls import rls_bypass
from core.services.audit import AuditService
from payments.models import CustomerReceipt, ReceiptStatus
from purchases.models import PurchaseCreditNote, PurchaseInvoice
from sales.models import SalesCreditNote, SalesInvoice


class Command(BaseCommand):
    help = (
        "Print completed documents with no audit row, and complaints that "
        "already have both a return and a credit note. "
        "--apply writes a labeled audit backfill and clears a credit-note "
        "pointer that belongs to the complaint's return. It does not cancel "
        "credit notes. Campaign ROI has nothing to backfill."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write labeled audit backfill rows and repair complaint pointers.",
        )

    def handle(self, *args, **options):
        apply = bool(options["apply"])
        self.stdout.write("campaign_roi=computed_on_read source=completed_invoice_taxable_net")
        with rls_bypass():
            self._missing_audits(SalesInvoice, SalesInvoice.Status.COMPLETED, "SalesInvoice", apply)
            self._missing_audits(PurchaseInvoice, PurchaseInvoice.Status.COMPLETED, "PurchaseInvoice", apply)
            self._missing_audits(SalesCreditNote, SalesCreditNote.Status.COMPLETED, "SalesCreditNote", apply)
            self._missing_audits(
                PurchaseCreditNote, PurchaseCreditNote.Status.COMPLETED, "PurchaseCreditNote", apply,
            )
            receipts = CustomerReceipt.objects.filter(status=ReceiptStatus.POSTED)
            self._missing_from_qs(receipts, "CustomerReceipt", apply, suffix=".created")
            self._complaints(apply)

    def _missing_audits(self, model, status, entity_type, apply):
        self._missing_from_qs(model.objects.filter(status=status), entity_type, apply)

    def _missing_from_qs(self, qs, entity_type, apply, suffix=".completed"):
        # Load ids first. A server-side iterator cannot run the audit lookup
        # on the same PostgreSQL connection. Only the lifecycle row counts: a
        # CREATE row or a later "edited" row does not show the document was
        # audited when it completed.
        pairs = list(qs.values_list("pk", "company_id"))
        existing = set(
            AuditEvent.objects.filter(entity_type=entity_type)
            .filter(Q(description__endswith=suffix) | Q(description__startswith="backfill:"))
            .values_list("company_id", "entity_id")
        )
        missing = [(pk, company_id) for pk, company_id in pairs if (company_id, str(pk)) not in existing]
        counts: dict[int, int] = {}
        for _pk, company_id in missing:
            counts[company_id] = counts.get(company_id, 0) + 1
        self.stdout.write(f"{entity_type}_completed_without_audit")
        if not counts:
            self.stdout.write("  none")
        else:
            for company_id, count in sorted(counts.items()):
                self.stdout.write(f"  company={company_id} count={count}")
        written = 0
        if apply:
            for pk, _company_id in missing:
                if self._backfill(qs.model, pk, entity_type, suffix):
                    written += 1
            self.stdout.write(f"  backfilled={written}")

    def _backfill(self, model, pk, entity_type, suffix=".completed") -> bool:
        row = model.objects.select_related("company").get(pk=pk)
        if AuditEvent.objects.filter(
            company_id=row.company_id, entity_type=entity_type, entity_id=str(row.pk),
        ).filter(Q(description__endswith=suffix) | Q(description__startswith="backfill:")).exists():
            return False
        AuditService.log(
            company=row.company,
            user=getattr(row, "updated_by", None) or getattr(row, "created_by", None),
            action="UPDATE",
            entity_type=entity_type,
            entity_id=str(row.pk),
            description="backfill: completed document had no audit row",
            metadata={
                "backfill": True,
                "source": "fmea2_existing_gaps",
                "status": str(getattr(row, "status", "") or ""),
                "number": str(getattr(row, "number", "") or ""),
            },
        )
        return True

    def _complaints(self, apply):
        both = Complaint.objects.filter(
            sales_return_id__isnull=False, sales_credit_note_id__isnull=False,
        ).select_related("sales_return", "sales_credit_note").order_by("company_id", "id")
        rows = list(both)
        self.stdout.write(f"complaints_with_return_and_credit_note={len(rows)}")
        repaired = 0
        for row in rows:
            self.stdout.write(
                f"  company={row.company_id} complaint={row.pk} "
                f"return={row.sales_return_id} credit_note={row.sales_credit_note_id}"
            )
            if not apply:
                continue
            if self._repair_complaint(row):
                repaired += 1
        if apply:
            self.stdout.write(f"  complaints_repaired={repaired}")

    def _repair_complaint(self, complaint) -> bool:
        note = complaint.sales_credit_note
        if note is None:
            return False
        same_return = note.sales_return_id is not None and note.sales_return_id == complaint.sales_return_id
        if same_return or note.status == SalesCreditNote.Status.CANCELLED:
            complaint.sales_credit_note = None
            complaint.save(update_fields=["sales_credit_note", "updated_at"])
            self.stdout.write(f"    cleared credit_note pointer complaint={complaint.pk}")
            return True
        self.stdout.write(
            f"    left complaint={complaint.pk} credit_note={note.pk} status={note.status} "
            "separate_document=1"
        )
        return False
