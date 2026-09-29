"""One-off backfill audit (security addendum, 2026-09-25).

`evaluate_referral_reward()` did not compare the referrer's identity against
the actual customer on the won opportunity before this fix, so some
already-issued `ReferralReward` rows may in fact be self-referrals that
should not have been created as PENDING (payable) in the first place.

This command scans existing PENDING rows and reports which ones would now
fail the new self-referral check, so an operator can review them before
approving or paying anything out. It never modifies a row — a human should
look at each flagged reward and reject it via the normal
`POST /api/v1/crm/referrals/rewards/{id}/reject/` action if it really is a
self-referral, since this touches money commitments already made to a
referrer.

Usage:
    python manage.py audit_referral_self_matches
    python manage.py audit_referral_self_matches --company 42
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from crm.models import ReferralReward
from crm.referrals import _referral_self_check


class Command(BaseCommand):
    help = (
        "Scan PENDING ReferralReward rows for probable self-referrals under the "
        "new identity check. Report only — never writes to existing rows."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--company", type=int, default=None,
            help="Limit the scan to one company id (default: all companies).",
        )

    def handle(self, *args, **options):
        qs = ReferralReward.objects.filter(reward_status=ReferralReward.Status.PENDING).select_related(
            "referral_code",
            "referral_code__referrer_customer",
            "referral_code__referrer_user",
            "referral_code__referrer_user__user",
            "opportunity",
            "opportunity__customer",
            "lead",
        )
        company_id = options.get("company")
        if company_id:
            qs = qs.filter(company_id=company_id)

        scanned = 0
        flagged = []
        for reward in qs.iterator():
            scanned += 1
            code = reward.referral_code
            referee = reward.opportunity.customer if reward.opportunity_id else None
            # Delegate to the same check evaluate_referral_reward() uses,
            # including its lead-identity fallback for a won opportunity that
            # has no customer attached — a hand-rolled re-check here
            # previously skipped exactly those rows.
            if _referral_self_check(code, referee, lead=reward.lead):
                flagged.append(reward)

        self.stdout.write(f"Scanned {scanned} PENDING referral reward(s).")
        if not flagged:
            self.stdout.write(self.style.SUCCESS("No probable self-referrals found."))
            return

        self.stdout.write(self.style.WARNING(
            f"{len(flagged)} PENDING reward(s) look like self-referrals under the new check. "
            "Review each manually and reject via the API if confirmed — this command makes no changes:"
        ))
        for reward in flagged:
            code = reward.referral_code
            referrer_label = (
                f"customer:{code.referrer_customer_id}"
                if code.referrer_customer_id
                else f"employee(user):{code.referrer_user_id}"
            )
            self.stdout.write(
                "  reward_id=%s company_id=%s opportunity_id=%s referral_code=%s "
                "referrer=%s referee_customer_id=%s reward_amount=%s"
                % (
                    reward.id,
                    reward.company_id,
                    reward.opportunity_id,
                    code.code,
                    referrer_label,
                    reward.opportunity.customer_id,
                    reward.reward_amount,
                )
            )
