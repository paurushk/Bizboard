"""Turn on grantable modules for one development company.

Payroll has no pack grant. ``--with-dark`` sets the manufacturing and
insurance pack keys only when the company has no subscription. It does not
write ENABLE_MANUFACTURING, ENABLE_PAYROLL, or ENABLE_CRM. On a subscribed
company those pack keys stay unset and the command says payroll stays off.
``--with-manufacturing-pack`` and ``--with-insurance-pack`` set the pack keys.

Refuses when DJANGO_ENV is production or staging. Does not write
ENABLE_GSTN_JSON or ENABLE_PREDICTIVE_DUNNING. Leaves the trial plan row
untouched. Does not turn on ai_features_enabled.
"""

from __future__ import annotations

import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounting.services import seed_chart_of_accounts
from accounts.models import CompanyUser, User
from core.services.feature_flags import (
    DARK_MODULE_KEYS,
    ROLLOUT_GRANTABLE_KEYS,
    build_feature_flags,
)

# Needs third-party credentials on the deployment; the screen is visible once the
# env ceiling is on, but live sending / payments need real keys. Never granted here.
CREDENTIAL_BACKED = (
    "ENABLE_WHATSAPP_CLOUD",
    "ENABLE_TELEGRAM",
    "ENABLE_ACCOUNT_AGGREGATOR",
    "ENABLE_CASHFREE",
    "ENABLE_PAYU",
)
# Deny-only keys: the env ceiling alone decides. Reported, not written.
ENV_ONLY_MODULES = ("ENABLE_FIXED_ASSETS", "ENABLE_BOE", "ENABLE_ARCH05_STATUTORY_FORMS")


class Command(BaseCommand):
    help = (
        "Enable grantable modules for one development company. "
        "Payroll has no pack grant. Staging and production are refused."
    )

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="Any user of the target company.")
        parser.add_argument("--company-id", type=int, help="Required when the user has several companies.")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--with-aa-consent",
            action="store_true",
            help="Also set ENABLE_AA_CONSENT. Default leaves Account Aggregator consent off.",
        )
        parser.add_argument(
            "--with-dark",
            action="store_true",
            help="On a company with no subscription, set the manufacturing and insurance pack keys. Never writes payroll.",
        )
        parser.add_argument(
            "--with-manufacturing-pack",
            action="store_true",
            help="Set manufacturing_pack_grant. Does not set ENABLE_MANUFACTURING by itself.",
        )
        parser.add_argument(
            "--with-insurance-pack",
            action="store_true",
            help="Set pack_grant=insurance. That turns CRM on. It does not set ENABLE_CRM by itself.",
        )

    def handle(self, *args, **options):
        from billing.services import plan_modules_for_company

        env_name = (getattr(settings, "DJANGO_ENV", "") or "").strip().lower()
        if env_name in ("production", "staging"):
            raise CommandError(f"Refusing to run when DJANGO_ENV={env_name}.")
        if os.environ.get("E2E_GOLDEN_GRANT") == "1":
            raise CommandError("Refusing to run while E2E_GOLDEN_GRANT=1.")
        user = User.objects.filter(email__iexact=options["email"]).first()
        if user is None:
            raise CommandError("No user with that email.")
        memberships = list(
            CompanyUser.objects.filter(user=user, is_active=True).select_related("company")
        )
        if not memberships:
            raise CommandError("That user has no company.")
        company_id = options.get("company_id")
        if len(memberships) > 1 and not company_id:
            raise CommandError("That user has several companies. Pass --company-id.")
        if company_id:
            membership = next((row for row in memberships if row.company_id == company_id), None)
            if membership is None:
                raise CommandError("That company is not one of this user's memberships.")
        else:
            membership = memberships[0]
        company = membership.company

        skipped = {"ENABLE_GSTN_JSON", "ENABLE_PREDICTIVE_DUNNING", *DARK_MODULE_KEYS}
        wanted = sorted(set(ROLLOUT_GRANTABLE_KEYS) - skipped)
        flags = dict(company.feature_flags or {})
        for key in wanted:
            flags[key] = True
        flags.pop("NAV_PACK_DEFAULT", None)
        if options["with_manufacturing_pack"]:
            flags["manufacturing_pack_grant"] = True
        if options["with_insurance_pack"]:
            flags["pack_grant"] = "insurance"
        if options["with_aa_consent"]:
            flags["ENABLE_AA_CONSENT"] = True
        if options["with_dark"]:
            if plan_modules_for_company(company) is None:
                flags["manufacturing_pack_grant"] = True
                flags["pack_grant"] = "insurance"
                for key in DARK_MODULE_KEYS:
                    flags.pop(key, None)
                self.stdout.write(
                    "Payroll stays off because no pack grants it. "
                    "Set manufacturing_pack_grant and pack_grant=insurance."
                )
            else:
                self.stdout.write(
                    "Payroll stays off because no pack grants it. "
                    "CRM needs --with-insurance-pack. Manufacturing needs --with-manufacturing-pack."
                )

        if not options["dry_run"]:
            company.feature_flags = flags
            company.accounting_enabled = True
            company.save(update_fields=["feature_flags", "accounting_enabled", "updated_at"])
            seed_chart_of_accounts(company)
            if hasattr(company, "_feature_flags_cache"):
                del company._feature_flags_cache

        effective = build_feature_flags(company=company) if not options["dry_run"] else {}
        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(f"{prefix}Company {company.pk} ({company.name}): requested {len(wanted)} modules.")
        if options["dry_run"]:
            return
        still_off = [k for k in wanted if not effective.get(k)]
        for key in still_off:
            self.stdout.write(f"  still off: {key} (check the plan module list)")
        for key in ENV_ONLY_MODULES:
            state = "on" if effective.get(key) else "off (env ceiling; set it on the deployment)"
            self.stdout.write(f"  env-only: {key} is {state}")
        for key in CREDENTIAL_BACKED:
            state = "screen on" if effective.get(key) else "off (needs env flag and credentials)"
            self.stdout.write(f"  integration: {key} is {state}")
        self.stdout.write(f"  enabled: {len(wanted) - len(still_off)} of {len(wanted)}")
