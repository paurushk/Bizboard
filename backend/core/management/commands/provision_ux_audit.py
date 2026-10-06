"""Create the UX audit company and the pack-sidebar control company.

Dev only. Refuses production and staging. Writes passwords to a gitignored
file and never prints them. Does not create a subscription, does not turn on
AI consent, and does not turn on Account Aggregator consent.

    python manage.py provision_ux_audit
    python manage.py provision_ux_audit --credentials-file C:\\tmp\\ux.txt
"""

from __future__ import annotations

import secrets
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import Company, CompanyUser, User
from billing.models import Plan, Subscription
from core.services.feature_flags import DARK_MODULE_KEYS, ROLLOUT_GRANTABLE_KEYS

from inventory.models import Warehouse
from masters.models import Customer, Product, Supplier, Unit

AUDIT_NAME = "UX Audit Traders"
CONTROL_NAME = "UX Pack Control"

AUDIT_USERS = (
    ("ux-audit-owner@bizboard.local", CompanyUser.Role.OWNER, "UX Audit Owner"),
    ("ux-audit-accountant@bizboard.local", CompanyUser.Role.ACCOUNTANT, "UX Audit Accountant"),
    ("ux-audit-auditor@bizboard.local", CompanyUser.Role.AUDITOR, "UX Audit Auditor"),
    ("ux-audit-inventory@bizboard.local", CompanyUser.Role.INVENTORY_STAFF, "UX Audit Inventory"),
    ("ux-audit-sales@bizboard.local", CompanyUser.Role.SALES_STAFF, "UX Audit Sales"),
    # Insurance screens need can_manage_policies, which only this role carries.
    ("ux-audit-policy@bizboard.local", CompanyUser.Role.POLICY_DESK, "UX Audit Policy Desk"),
)

OWNER_CAPS = {
    "can_manage_inventory": True,
    "can_import": True,
    "can_cancel_documents": True,
    "can_view_financial_reports": True,
    "can_export": True,
    "can_view_ai_insights": True,
    "can_use_ai_assistant": True,
    "can_create_sales": True,
    "can_create_purchases": True,
    "can_create_payments": True,
    "can_post_journals": True,
}


def _refuse_unless_dev() -> None:
    env_name = (getattr(settings, "DJANGO_ENV", "") or "").strip().lower()
    # The dockerised dev stack runs DEBUG=0 (settings refuse DEBUG with non-local hosts), so an
    # explicit DJANGO_ENV=development counts as dev. Production and staging are always refused.
    dev = env_name == "development" or bool(getattr(settings, "DEBUG", False))
    if env_name in ("production", "staging") or not dev:
        raise CommandError(
            f"provision_ux_audit refuses to run outside dev (DJANGO_ENV={env_name or 'unset'})."
        )


def _default_credentials_path() -> Path:
    return Path(settings.BASE_DIR).parent / ".ux-audit-credentials.local"


def _read_passwords(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    found: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 3 and parts[2] and parts[2] != "UNCHANGED":
            found[parts[0]] = parts[2]
    return found


def _write_credentials(path: Path, rows: list[tuple[str, str, str]]) -> None:
    lines = [
        "# Local only. Gitignored. Do not commit or paste into chat.",
        "# email, role, password",
    ]
    for email, role, password in rows:
        lines.append(f"{email}\t{role}\t{password}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _ensure_user(email: str, full_name: str, password: str | None) -> tuple[User, str]:
    user = User.objects.filter(email__iexact=email).first()
    if user is not None:
        return user, password or ""
    chosen = password or secrets.token_urlsafe(18)
    user = User.objects.create_user(email=email, password=chosen, full_name=full_name)
    return user, chosen


def _caps_for(role: str) -> dict:
    if role == CompanyUser.Role.OWNER:
        return dict(OWNER_CAPS)
    defaults = CompanyUser.capability_defaults_for_role(role) or {}
    return dict(defaults)


def _ensure_membership(company: Company, user: User, role: str) -> None:
    membership = CompanyUser.objects.filter(company=company, user=user).first()
    caps = _caps_for(role)
    if membership is None:
        CompanyUser.objects.create(company=company, user=user, role=role, **caps)
        return
    membership.role = role
    for key, value in caps.items():
        setattr(membership, key, value)
    membership.save()


FULL_DEMO_PLAN_SLUG = "ux-full-demo"


def _ensure_full_demo_plan(company: Company) -> None:
    """Point the audit company at a plan that names every module.

    A company gets a trial subscription on first login, and the trial plan leaves the dark
    modules (CRM, manufacturing, payroll) unnamed, so they turn off (Holistic decision 4).
    The sanctioned per-company path is a plan that names them (H5.1). This never edits the
    shared ``trial`` plan row.
    """
    modules = {key: True for key in sorted(set(DARK_MODULE_KEYS) | set(ROLLOUT_GRANTABLE_KEYS))}
    plan, _ = Plan.objects.get_or_create(
        slug=FULL_DEMO_PLAN_SLUG,
        defaults={"name": "UX full demo", "seat_limit": 50, "modules": modules, "is_active": True},
    )
    if plan.modules != modules:
        plan.modules = modules
        plan.save(update_fields=["modules", "updated_at"])
    sub = Subscription.objects.filter(company=company).first()
    if sub is None:
        Subscription.objects.create(
            company=company, plan=plan, status=Subscription.Status.TRIAL,
            trial_ends_at=timezone.now() + timedelta(days=3650),
        )
    elif sub.plan_id != plan.id:
        sub.plan = plan
        sub.save(update_fields=["plan", "updated_at"])


def _ensure_masters(company: Company) -> None:
    if not Unit.objects.filter(company=company).exists():
        unit = Unit.objects.create(company=company, name="Piece", short_name="pcs")
    else:
        unit = Unit.objects.filter(company=company).first()
    if not Customer.objects.filter(company=company).exists():
        Customer.objects.create(
            company=company,
            name="UX Audit Customer",
            state="Karnataka",
            phone="9000000301",
            gstin="29AABCU9603R1ZJ",
        )
    if not Supplier.objects.filter(company=company).exists():
        Supplier.objects.create(
            company=company,
            name="UX Audit Supplier",
            state="Karnataka",
            phone="9000000302",
            gstin="29AAACW3775F1Z2",
        )
    if not Product.objects.filter(company=company).exists():
        Product.objects.create(
            company=company,
            name="UX Audit Item",
            sku="UXH-ITEM",
            hsn_code="8471",
            gst_rate=Decimal("18"),
            purchase_price=Decimal("80"),
            selling_price=Decimal("100"),
            mrp=Decimal("120"),
            unit=unit,
            reorder_level=Decimal("5"),
        )
    if not Warehouse.objects.filter(company=company, is_default=True).exists():
        Warehouse.objects.create(
            company=company, name="Main", code="MAIN", is_default=True, is_active=True,
        )


class Command(BaseCommand):
    help = "Create UX Audit Traders (full menu, no subscription, no AI consent) and UX Pack Control."

    def add_arguments(self, parser):
        parser.add_argument(
            "--credentials-file",
            default="",
            help="Where to write passwords. Default: <repo>/.ux-audit-credentials.local",
        )
        parser.add_argument(
            "--skip-history",
            action="store_true",
            help="Do not seed six months of draft history.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        _refuse_unless_dev()
        path = Path(options["credentials_file"]) if options["credentials_file"] else _default_credentials_path()
        existing_passwords = _read_passwords(path)
        credential_rows: list[tuple[str, str, str]] = []

        audit = Company.objects.filter(name=AUDIT_NAME).first()
        if audit is None:
            audit = Company.objects.create(
                name=AUDIT_NAME,
                legal_name="UX Audit Traders",
                state="Karnataka",
                address="1, Audit Lane",
                city="Bengaluru",
                pincode="560001",
                phone="08040000001",
                email="billing@ux-audit.local",
                assume_local_state_for_blank_party=True,
                negative_stock_policy=Company.NegativeStockPolicy.BLOCK,
                tax_profile_confirmed_at=timezone.now(),
            )
        audit.ai_features_enabled = False
        audit.save(update_fields=["ai_features_enabled", "updated_at"])

        owner_email = AUDIT_USERS[0][0]
        for email, role, full_name in AUDIT_USERS:
            prior = existing_passwords.get(email)
            user, chosen = _ensure_user(email, full_name, prior or None)
            if not prior and chosen:
                existing_passwords[email] = chosen
            _ensure_membership(audit, user, role)
            credential_rows.append((email, role, existing_passwords.get(email, "UNCHANGED")))

        _ensure_masters(audit)

        control = Company.objects.filter(name=CONTROL_NAME).first()
        if control is None:
            control = Company.objects.create(
                name=CONTROL_NAME,
                legal_name="UX Pack Control",
                state="Karnataka",
                city="Bengaluru",
                feature_flags={"NAV_PACK_DEFAULT": True},
                ai_features_enabled=False,
                accounting_enabled=False,
            )
        else:
            flags = dict(control.feature_flags or {})
            flags["NAV_PACK_DEFAULT"] = True
            control.feature_flags = flags
            control.ai_features_enabled = False
            control.save(update_fields=["feature_flags", "ai_features_enabled", "updated_at"])

        control_email = "ux-pack-control@bizboard.local"
        prior = existing_passwords.get(control_email)
        control_user, chosen = _ensure_user(control_email, "UX Pack Control", prior or None)
        if not prior and chosen:
            existing_passwords[control_email] = chosen
        _ensure_membership(control, control_user, CompanyUser.Role.OWNER)
        credential_rows.append(
            (control_email, CompanyUser.Role.OWNER, existing_passwords.get(control_email, "UNCHANGED"))
        )

        _write_credentials(path, credential_rows)
        self.stdout.write(f"Credentials file: {path}")
        self.stdout.write("Passwords are in that file only.")

        _ensure_full_demo_plan(audit)
        call_command("enable_full_demo", email=owner_email, stdout=self.stdout)
        audit.refresh_from_db()
        if audit.ai_features_enabled:
            audit.ai_features_enabled = False
            audit.save(update_fields=["ai_features_enabled", "updated_at"])

        if not options["skip_history"]:
            call_command(
                "seed_synthetic_bulk",
                company=AUDIT_NAME,
                history=True,
                stdout=self.stdout,
            )
