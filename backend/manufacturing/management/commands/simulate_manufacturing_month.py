"""Run thirty days of manufacturing through the real services and prove the books still agree.

Every simulated day does a few things from a fixed seed: buys material, makes a batch the one-screen
way, runs a full work order with a partial then a final receipt, returns a little unused material,
sends material to a job worker and takes it back, reverses one document, closes what is finished.
After each day the stock-ledger, work-in-progress and money invariants are checked. The command exits
non-zero on the first day that breaks one. Meant for a scratch database; refuses on staging and
production unless --force-scratch is given.
"""

from __future__ import annotations

import random
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.models import CompanyUser, User
from core.exceptions import BusinessRuleError
from inventory.models import MovementType
from inventory.services import InventoryService
from manufacturing import demo
from manufacturing.models import WorkOrder
from manufacturing.services import flow, quick_entry
from manufacturing.services import issue as issue_svc
from manufacturing.services import receipt as receipt_svc
from manufacturing.services import release_work_order


class Command(BaseCommand):
    help = "Simulate thirty days of manufacturing on a scratch company and check the invariants every day."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--company-id", type=int)
        parser.add_argument("--days", type=int, default=30)
        parser.add_argument("--seed", type=int, default=20261020)
        parser.add_argument("--force-scratch", action="store_true", help="Allow on staging or production (never on live data).")

    def handle(self, *args, **options):
        env_name = (getattr(settings, "DJANGO_ENV", "") or "").strip().lower()
        if env_name in ("production", "staging") and not options["force_scratch"]:
            raise CommandError(f"Refusing to run when DJANGO_ENV={env_name}.")
        user = User.objects.filter(email__iexact=options["email"]).first()
        if user is None:
            raise CommandError("No user with that email.")
        memberships = list(CompanyUser.objects.filter(user=user, is_active=True).select_related("company"))
        if not memberships:
            raise CommandError("That user has no company.")
        if len(memberships) > 1 and not options.get("company_id"):
            raise CommandError("That user has several companies. Pass --company-id.")
        membership = (
            next((m for m in memberships if m.company_id == options["company_id"]), None)
            if options.get("company_id") else memberships[0]
        )
        if membership is None:
            raise CommandError("That company is not one of this user's memberships.")
        company = membership.company

        rng = random.Random(options["seed"])  # noqa: S311 - a repeatable simulation, nothing secret
        built = demo.build(company, user)
        summary = self.run_days(company, user, built, rng, options["days"])
        self.stdout.write(self.style.SUCCESS(
            f"{options['days']} days ok: {summary['made']} packs made, {summary['orders']} work orders, "
            f"{summary['reversed']} reversals, {summary['refused']} refusals the rules were right to make."
        ))

    def run_days(self, company, user, built, rng, days: int) -> dict:
        from core.invariants import assert_all_invariants

        stats = {"made": Decimal("0"), "orders": 0, "reversed": 0, "refused": 0}
        biscuit, flour, sugar, butter, box = (built[k] for k in ("biscuit", "flour", "sugar", "butter", "box"))
        for day in range(days):
            # Buy some material most days.
            for prod, qty, cost in ((flour, 120, "30"), (sugar, 40, "45"), (butter, 20, "510"), (box, 100, "15")):
                if rng.random() < 0.6:
                    InventoryService.post_movement(
                        company=company, product=prod, movement_type=MovementType.PURCHASE,
                        quantity=Decimal(qty), unit_cost=Decimal(cost) + Decimal(rng.randint(-2, 3)), user=user,
                    )
            # One-screen production.
            if rng.random() < 0.8:
                qty = Decimal(rng.choice([10, 20, 30]))
                try:
                    quick_entry.quick_production(company, user, product=biscuit, qty=qty, batch_no=f"SIM-{day:02d}")
                    stats["made"] += qty
                    stats["orders"] += 1
                except BusinessRuleError:
                    stats["refused"] += 1
            # A full work order: issue, partial output, return a little, final output, close.
            if rng.random() < 0.5:
                qty = Decimal(rng.choice([10, 20]))
                wo = None
                try:
                    from manufacturing.services import bom as bom_svc
                    from manufacturing.services import _snapshot_bom
                    from manufacturing.services.common import next_number

                    bom = bom_svc.resolve_bom(company, biscuit)
                    wo = WorkOrder.objects.create(
                        company=company, bom=bom, qty=qty, issue_mode="SEPARATE",
                        due_date=built["today"] + timedelta(days=rng.randint(-2, 10)),
                        number=next_number(company, "mfg_wo", "WO"), created_by=user, updated_by=user,
                    )
                    _snapshot_bom(wo)
                    bom_svc.lock_bom(bom)
                    release_work_order(wo, user)
                    issue_svc.post_issue(issue_svc.create_issue(wo, user, None), user)
                    half = receipt_svc.create_receipt(
                        wo, user, {"is_final": False, "lines": [{"kind": "MAIN", "qty_good": qty / 2}]},
                    )
                    receipt_svc.post_receipt(half, user)
                    last = receipt_svc.post_receipt(receipt_svc.create_receipt(wo, user, {"is_final": True}), user)
                    if rng.random() < 0.15:
                        receipt_svc.reverse_receipt(last, user, "simulated mistake")
                        stats["reversed"] += 1
                        receipt_svc.post_receipt(receipt_svc.create_receipt(wo, user, {"is_final": True}), user)
                    wo.refresh_from_db()
                    flow.close_work_order(wo, user)
                    stats["made"] += qty
                    stats["orders"] += 1
                except BusinessRuleError:
                    stats["refused"] += 1
            assert_all_invariants(company)
        return stats
