"""Report (and optionally repair) credit-note data left behind by older behaviour (NEW-08).

Two findings:

1. Draft credit notes with reason SALES_RETURN that are not linked to a sales return.
   They can never be completed (stock lives on the return). ``--apply`` moves them
   to CORRECTION_OF_INVOICE so the user can finish or delete them.
2. Referral rewards marked PAID while their credit note is still a draft. The
   reward is paid only once the note is completed, so ``--apply`` puts the reward
   back to APPROVED; "Mark paid" then drafts-or-reuses and completes the note.

Dry run by default.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from sales.models import NoteReason, SalesCreditNote


class Command(BaseCommand):
    help = "Report or repair orphan SALES_RETURN credit-note drafts and referral rewards paid on draft notes."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Write the repairs (default: report only).")
        parser.add_argument("--company", type=int, default=None, help="Limit to one company id.")

    def handle(self, *args, **opts):
        apply = opts["apply"]
        company_id = opts["company"]

        notes = SalesCreditNote.objects.filter(
            status=SalesCreditNote.Status.DRAFT,
            reason=NoteReason.SALES_RETURN,
            sales_return__isnull=True,
        )
        if company_id:
            notes = notes.filter(company_id=company_id)
        self.stdout.write(f"Draft SALES_RETURN credit notes without a return: {notes.count()}")
        for note in notes:
            self.stdout.write(f"  note {note.pk} company {note.company_id} invoice {note.sales_invoice_id}")
        if apply:
            changed = notes.update(reason=NoteReason.CORRECTION_OF_INVOICE)
            self.stdout.write(self.style.SUCCESS(f"  moved {changed} to CORRECTION_OF_INVOICE"))

        from crm.models import ReferralReward

        rewards = ReferralReward.objects.filter(
            reward_status=ReferralReward.Status.PAID,
            credit_note__status=SalesCreditNote.Status.DRAFT,
        ).select_related("credit_note")
        if company_id:
            rewards = rewards.filter(company_id=company_id)
        self.stdout.write(f"Referral rewards PAID with a draft credit note: {rewards.count()}")
        for reward in rewards:
            self.stdout.write(f"  reward {reward.pk} company {reward.company_id} note {reward.credit_note_id}")
        if apply:
            with transaction.atomic():
                fixed = 0
                for reward in rewards:
                    reward.reward_status = ReferralReward.Status.APPROVED
                    reward.paid_at = None
                    reward.save(update_fields=["reward_status", "paid_at", "updated_at"])
                    fixed += 1
            self.stdout.write(self.style.SUCCESS(f"  reset {fixed} reward(s) to APPROVED"))
        if not apply:
            self.stdout.write("Dry run. Re-run with --apply to write the repairs.")
