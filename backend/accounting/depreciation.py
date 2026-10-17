"""ACS-52/54: depreciation planning, running and the schedule view.

The nightly task posts the last month for active assets and only looks back a few months.
This module is what an owner uses on the screen: preview, run through a chosen month, and see
the full month-by-month schedule of one asset.
"""
from __future__ import annotations

import copy
import datetime
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessRuleError

from .models import FixedAsset, JournalEntry
from .services import PostingService
from .tasks import _depreciation_already_posted, _month_end, _prorate_days_in_service

ZERO = Decimal("0.00")
MAX_SCHEDULE_MONTHS = 600


def method_label(asset) -> str:
    return "WDV" if asset.method == FixedAsset.Method.WDV else "SLM"


def narration(asset) -> str:
    return f"{method_label(asset)} depreciation: {asset.name}"


def last_completed_month_end(today: datetime.date | None = None) -> datetime.date:
    today = today or timezone.localdate()
    return today.replace(day=1) - datetime.timedelta(days=1)


def month_amount(asset, cm: datetime.date) -> Decimal:
    """What would be charged for month ``cm`` given the asset's current accumulated figure. No side effects."""
    floor = asset.salvage_value or ZERO
    remaining = asset.acquisition_cost - asset.depreciated_amount - floor
    if remaining <= 0:
        return ZERO
    amount = min(asset.monthly_depreciation, remaining)
    if amount <= 0:
        return ZERO
    amount = _prorate_days_in_service(asset, cm, amount)
    if amount <= 0:
        return ZERO
    if remaining - amount <= Decimal("1"):
        amount = remaining
    return amount


def _month_ends(start: datetime.date, through: datetime.date):
    cm = _month_end(start)
    guard = 0
    while cm <= through and guard < MAX_SCHEDULE_MONTHS:
        yield cm
        cm = _month_end(cm + datetime.timedelta(days=1))
        guard += 1


def plan_asset(asset, through: datetime.date) -> list[dict]:
    """Months from the acquisition month to ``through`` that still need a charge, in order."""
    sim = copy.copy(asset)
    rows = []
    for cm in _month_ends(asset.acquisition_date, through):
        key = f"{cm:%Y-%m}"
        if _depreciation_already_posted(asset, cm):
            continue
        amount = month_amount(sim, cm)
        if amount <= 0:
            continue
        rows.append({"month": key, "month_end": cm, "amount": amount})
        sim.depreciated_amount = sim.depreciated_amount + amount
    return rows


def plan_company(company, through: datetime.date) -> list[dict]:
    out = []
    for asset in FixedAsset.objects.filter(company=company, status=FixedAsset.Status.ACTIVE).order_by("id"):
        months = plan_asset(asset, through)
        if months:
            out.append({"asset": asset, "months": months})
    return out


def post_month(locked, cm: datetime.date, user=None) -> Decimal:
    """Post one month for an asset already row-locked. Raises BusinessRuleError when the month is closed."""
    amount = month_amount(locked, cm)
    if amount <= 0:
        return ZERO
    entry = PostingService.post(
        company=locked.company,
        source_type="FIXED_ASSET",
        source_id=locked.id,
        purpose=f"DEPRECIATION-{cm:%Y-%m}",
        entry_date=cm,
        user=user,
        narration=narration(locked),
        lines=[
            {"account": locked.depreciation_expense_account, "debit": amount},
            {"account": locked.accumulated_depreciation_account, "credit": amount},
        ],
    )
    if entry is None:
        return ZERO
    locked.depreciated_amount = locked.depreciated_amount + amount
    return amount


def run_company(company, user, through: datetime.date, *, dry_run: bool = False) -> dict:
    """Post every missing month up to ``through`` for the company's active assets.

    A month that cannot post (closed period, no books) is reported against its asset and the rest continue.
    """
    if through > last_completed_month_end():
        raise BusinessRuleError("Depreciation can be run only for months that have ended.", code="dep_month_not_ended")
    results, posted, total = [], 0, ZERO
    for item in plan_company(company, through):
        asset = item["asset"]
        row = {"asset": asset.pk, "name": asset.name, "months": [], "errors": []}
        if dry_run:
            row["months"] = [{"month": m["month"], "amount": str(m["amount"]), "status": "would_post"} for m in item["months"]]
            results.append(row)
            continue
        errors: list[str] = []
        with transaction.atomic():
            locked = FixedAsset.objects.select_for_update().get(pk=asset.pk, company=company)
            for m in plan_asset(locked, through):
                cm = m["month_end"]
                try:
                    with transaction.atomic():
                        amount = post_month(locked, cm, user)
                except BusinessRuleError as exc:
                    errors.append(f"{m['month']}: {exc.detail if hasattr(exc, 'detail') else exc}")
                    row["months"].append({"month": m["month"], "amount": str(m["amount"]), "status": "blocked"})
                    continue
                if amount > 0:
                    posted += 1
                    total += amount
                    row["months"].append({"month": m["month"], "amount": str(amount), "status": "posted"})
            posted_keys = {x["month"] for x in row["months"] if x["status"] == "posted"}
            still = [k for k in (locked.depreciation_catchup_months or "").split(",") if k and k not in posted_keys]
            locked.depreciation_catchup_months = ",".join(still)[:800]
            locked.last_depreciation_error = "; ".join(errors)[:500]
            locked.save(update_fields=["depreciated_amount", "depreciation_catchup_months", "last_depreciation_error", "updated_at"])
        row["errors"] = errors
        results.append(row)
    return {"through": f"{through:%Y-%m}", "dry_run": dry_run, "posted": posted, "total": str(total), "assets": results}


def post_disposal_month(locked, disposal_date: datetime.date, user=None) -> Decimal:
    """Charge the part-month up to the sale so the disposal sees the right book value (ACS-12 follow-up)."""
    previous = locked.disposed_at
    locked.disposed_at = disposal_date
    try:
        cm = _month_end(disposal_date)
        if _depreciation_already_posted(locked, cm):
            return ZERO
        return post_month(locked, cm, user)
    finally:
        locked.disposed_at = previous


def schedule(asset) -> dict:
    """Every month of the asset's life: what was charged, what is missing, what is still to come."""
    entries = {
        e.purpose[len("DEPRECIATION-"):]: e
        for e in JournalEntry.objects.filter(
            company=asset.company, source_type="FIXED_ASSET", source_id=asset.pk,
            status=JournalEntry.Status.POSTED, purpose__startswith="DEPRECIATION-",
        ).prefetch_related("lines")
    }
    sim = copy.copy(asset)
    sim.depreciated_amount = ZERO
    today_end = last_completed_month_end()
    horizon = _month_end(asset.acquisition_date + datetime.timedelta(days=31 * 600))
    rows = []
    for cm in _month_ends(asset.acquisition_date, horizon):
        key = f"{cm:%Y-%m}"
        entry = entries.get(key)
        if entry is not None:
            amount = sum((line.credit for line in entry.lines.all()), ZERO)
            sim.depreciated_amount = sim.depreciated_amount + amount
            rows.append({
                "month": key, "amount": str(amount), "status": "posted", "journal_id": entry.pk, "number": entry.number,
                "accumulated": str(sim.depreciated_amount),
            })
            continue
        if asset.status == FixedAsset.Status.DISPOSED and asset.disposed_at and cm > _month_end(asset.disposed_at):
            break
        amount = month_amount(sim, cm)
        if amount <= 0:
            if sim.acquisition_cost - sim.depreciated_amount - (sim.salvage_value or ZERO) <= 0:
                break
            continue
        sim.depreciated_amount = sim.depreciated_amount + amount
        rows.append({
            "month": key, "amount": str(amount), "status": "missing" if cm <= today_end else "projected",
            "journal_id": None, "number": "", "accumulated": str(sim.depreciated_amount),
        })
    disposal = None
    entry = JournalEntry.objects.filter(
        company=asset.company, source_type="FIXED_ASSET", source_id=asset.pk, purpose="DISPOSAL",
        status=JournalEntry.Status.POSTED,
    ).first()
    if entry is not None:
        disposal = {"journal_id": entry.pk, "number": entry.number, "date": entry.entry_date.isoformat()}
    return {"asset": asset.pk, "rows": rows, "disposal": disposal}
