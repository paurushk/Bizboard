"""GST-08: Bill of Entry (import ITC) lifecycle."""

from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessRuleError

from .models import BillOfEntry


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

        from reporting.gst_periods import assert_period_allows_money_amend

        assert_period_allows_money_amend(locked.company, locked.boe_date)

        locked.status = BillOfEntry.Status.COMPLETED
        locked.completed_at = timezone.now()
        locked.updated_by = user
        locked.save(update_fields=["status", "completed_at", "updated_by", "updated_at"])

        if getattr(locked.company, "accounting_enabled", False):
            from accounting.services import PostingService

            PostingService.post_bill_of_entry(locked, user=user)
        return locked

    @staticmethod
    @transaction.atomic
    def cancel(boe: BillOfEntry, user=None) -> BillOfEntry:
        locked = BillOfEntry.objects.select_for_update().get(pk=boe.pk)
        if locked.status == BillOfEntry.Status.CANCELLED:
            return locked
        if locked.status == BillOfEntry.Status.COMPLETED:
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
        return locked
