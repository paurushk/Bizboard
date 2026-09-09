"""GST-08: Bill of Entry (import ITC) lifecycle."""

from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessRuleError

from .models import BillOfEntry


def _assert_boe_import_itc_reconciled(boe: BillOfEntry) -> None:
    """B3-022: mirror `assert_claimable_itc_allowed` for import ITC.

    If the availing period already has GSTR-2B ingest, ELIGIBLE import ITC on a
    Bill of Entry must be reconciled against ICEGATE / GSTR-2B (table IMPG)
    before Complete posts it. No 2B data for the period -> no gate (same escape
    hatch the domestic-ITC check uses).
    """
    if boe.itc_eligibility != BillOfEntry.ItcEligibility.ELIGIBLE:
        return
    if boe.icegate_verified:
        return
    period = boe.resolved_itc_period()
    if not period:
        return
    from reporting.models import Gstr2bIngest

    if not Gstr2bIngest.objects.filter(company=boe.company, period=period).exists():
        return
    raise BusinessRuleError(
        "Import ITC on this Bill of Entry can't be claimed until it's reconciled "
        f"against ICEGATE / GSTR-2B (table IMPG) for {period}. Verify the BoE in "
        "ICEGATE and set icegate_verified, or mark the ITC INELIGIBLE."
    )


class BillOfEntryService:
    @staticmethod
    @transaction.atomic
    def complete(boe: BillOfEntry, user=None) -> BillOfEntry:
        locked = BillOfEntry.objects.select_for_update().get(pk=boe.pk)
        if locked.status == BillOfEntry.Status.COMPLETED:
            return locked
        if locked.status == BillOfEntry.Status.CANCELLED:
            raise BusinessRuleError("A cancelled Bill of Entry cannot be completed.")
        if locked.total_customs_paid <= 0:
            raise BusinessRuleError("A Bill of Entry needs a non-zero IGST / cess / BCD amount.")
        _assert_boe_import_itc_reconciled(locked)

        from reporting.gst_periods import (
            assert_period_allows_money_amend,
            mark_period_dirty_if_snapshotted,
        )

        assert_period_allows_money_amend(locked.company, locked.boe_date)

        locked.status = BillOfEntry.Status.COMPLETED
        locked.completed_at = timezone.now()
        locked.updated_by = user
        locked.save(update_fields=["status", "completed_at", "updated_by", "updated_at"])

        if getattr(locked.company, "accounting_enabled", False):
            from accounting.services import PostingService

            PostingService.post_bill_of_entry(locked, user=user)
        # B3-008: import ITC (3B 4(A)(5)) moved — flag any GSTR-3B snapshot stale.
        mark_period_dirty_if_snapshotted(locked.company, locked.boe_date)
        return locked

    @staticmethod
    @transaction.atomic
    def cancel(boe: BillOfEntry, user=None) -> BillOfEntry:
        locked = BillOfEntry.objects.select_for_update().get(pk=boe.pk)
        if locked.status == BillOfEntry.Status.CANCELLED:
            return locked
        # CR-044: block cancel when a completed purchase still links this BoE.
        from purchases.models import PurchaseInvoice

        linked = PurchaseInvoice.objects.filter(
            company=locked.company,
            bill_of_entry=locked,
            status=PurchaseInvoice.Status.COMPLETED,
        ).exists()
        if linked:
            raise BusinessRuleError(
                "Cannot cancel a Bill of Entry while a completed purchase invoice "
                "still links it. Cancel or unlink that purchase first."
            )
        # CR-098: draft PIs linking this BoE would fail Complete after cancel.
        draft_linked = PurchaseInvoice.objects.filter(
            company=locked.company,
            bill_of_entry=locked,
        ).exclude(
            status__in=(PurchaseInvoice.Status.COMPLETED, PurchaseInvoice.Status.CANCELLED)
        )
        if draft_linked.exists():
            draft_linked.update(bill_of_entry=None)
        was_completed = locked.status == BillOfEntry.Status.COMPLETED
        if was_completed:
            from reporting.gst_periods import assert_period_allows_money_amend

            assert_period_allows_money_amend(
                locked.company, locked.boe_date, allow_soft_closed=True
            )
            if getattr(locked.company, "accounting_enabled", False):
                from accounting.services import PostingService

                PostingService.reverse_bill_of_entry(locked, user=user)
        locked.status = BillOfEntry.Status.CANCELLED
        locked.cancelled_at = timezone.now()
        locked.updated_by = user
        locked.save(update_fields=["status", "cancelled_at", "updated_by", "updated_at"])
        if was_completed:
            # B3-008: reversing posted import ITC — flag the 3B snapshot stale.
            from reporting.gst_periods import mark_period_dirty_if_snapshotted

            mark_period_dirty_if_snapshotted(locked.company, locked.boe_date)
        return locked
