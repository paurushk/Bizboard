"""Named flag bundles. Entitlement and hand edits win over a pack."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from billing.services import plan_modules_for_company
from core.services.flag_observability import log_flag_event

# Proposed split for review when the wizard is used. Payroll is absent.
# Internal ops flags (manufacturing, statutory forms, sandbox gateways) are absent.
PACKS = {
    "retail": (
        "ENABLE_POS",
        "ENABLE_REPLENISHMENT",
        "ENABLE_GST_GUARD",
        "ENABLE_CUSTOMER_PORTAL",
        "ENABLE_CUSTOMER_360",
        "ENABLE_PREDICTIVE_DUNNING",
        "ENABLE_ACTION_ASSIGNMENT",
        "ENABLE_GSTR",
    ),
    "trade": (
        "ENABLE_CRM",
        "ENABLE_REPLENISHMENT",
        "ENABLE_PURCHASE_PLANNING",
        "ENABLE_SUPPLIER_PRICE_HISTORY",
        "ENABLE_ROUTE_PROFIT",
        "ENABLE_ROUTE_OPTIMIZATION",
        "ENABLE_ORDER_GATES",
        "ENABLE_CUSTOMER_ACTIONS",
        "ENABLE_GST_GUARD",
        "ENABLE_GSTR",
        "ENABLE_TDS",
        "ENABLE_TALLY",
        "ENABLE_ACTION_ASSIGNMENT",
        "ENABLE_CUSTOMER_360",
    ),
    # Beat distribution. ENABLE_CRM is listed because the archetype uses it,
    # and _entitled still refuses that dark module on confirm.
    "distribution": (
        "ENABLE_CRM",
        "ENABLE_REPLENISHMENT",
        "ENABLE_PURCHASE_PLANNING",
        "ENABLE_SUPPLIER_PRICE_HISTORY",
        "ENABLE_ROUTE_PROFIT",
        "ENABLE_ROUTE_OPTIMIZATION",
        "ENABLE_ORDER_GATES",
        "ENABLE_CUSTOMER_ACTIONS",
        "ENABLE_GST_GUARD",
        "ENABLE_GSTR",
        "ENABLE_TDS",
        "ENABLE_TALLY",
        "ENABLE_ACTION_ASSIGNMENT",
        "ENABLE_CUSTOMER_360",
        "ENABLE_CROSS_SELL",
        "ENABLE_CUSTOMER_PORTAL",
        "ENABLE_PREDICTIVE_DUNNING",
    ),
    # Factory pack. ENABLE_MANUFACTURING is granted by this pack only.
    "manufacturing": (
        "ENABLE_REPLENISHMENT",
        "ENABLE_PURCHASE_PLANNING",
        "ENABLE_SUPPLIER_PRICE_HISTORY",
        "ENABLE_GST_GUARD",
        "ENABLE_GSTR",
        "ENABLE_TDS",
        "ENABLE_TALLY",
        "ENABLE_MANUFACTURING",
    ),
    # Insurance desk: CRM is a dark module. This pack is the one grant that
    # turns it on, together with referrals, tickets, and complaints.
    # Retail and trade still skip every dark key in _entitled.
    "insurance": (
        "ENABLE_CRM",
        "ENABLE_INSURANCE",
        "ENABLE_REFERRALS",
        "ENABLE_SUPPORT_TICKETS",
        "ENABLE_COMPLAINTS",
    ),
}

# Both archetype packs are approved. Payroll stays out of every pack.
HELD_PACKS = ()

QUESTIONS = ("what_you_sell", "how_you_sell", "deliver", "gst_registered")


def propose_pack(answers: dict) -> str:
    how = (answers.get("how_you_sell") or "").strip().lower()
    if how == "counter":
        return "retail"
    return "trade"


def _entitled(company, key: str) -> bool:
    """Match the flag service. A dark module a plan does not name stays off.

    ENABLE_CRM is both a dark module (env-gated deployment ceiling) and the
    first flag listed in PACKS["trade"] — that is intentional: the pack
    tuple documents what the archetype eventually gets, not an unconditional
    grant. A plan's `modules` JSON, including an explicit `True` for a dark
    key, must never entitle it here either — dark modules only come on
    through a real deployment-level grant, never through a pack confirm or a
    trial/plan module list.
    """
    from core.services.feature_flags import DARK_MODULE_KEYS

    if key in DARK_MODULE_KEYS:
        return False
    from billing.services import trial_plan_modules

    modules = plan_modules_for_company(company)
    # No subscription is the trial dict, not a grant. A key a real plan omits
    # stays allowed so older paid plans that never listed the flag keep working.
    if not isinstance(modules, dict):
        return bool(trial_plan_modules().get(key, False))
    if key in modules:
        return bool(modules[key])
    return True


def pack_preview(company, pack: str) -> dict:
    """What confirming ``pack`` would do, without changing anything (SET-09b).

    A pack only ever turns features on: it never turns one off and never touches data. Each key falls
    in exactly one list, using the same rules as `apply_pack`:

    * ``would_enable``: off now, and this pack will switch it on;
    * ``already_on``: already on for this company;
    * ``kept_as_set``: someone changed it by hand since a pack last set it, so it is left alone;
    * ``unavailable``: this plan or deployment does not include it, so it is skipped.
    """
    from accounts.models import CompanyPackState
    from core.exceptions import BusinessRuleError

    if pack not in PACKS:
        raise BusinessRuleError("Unknown pack.")
    state = CompanyPackState.objects.filter(company=company).first()
    snapshot = dict(state.applied_flags or {}) if state else {}
    flags = dict(company.feature_flags or {})
    out = {"pack": pack, "would_enable": [], "already_on": [], "kept_as_set": [], "unavailable": []}
    for key in PACKS[pack]:
        if key == "ENABLE_PAYROLL":
            continue
        granted_dark = (pack == "insurance" and key == "ENABLE_CRM") or (
            pack == "manufacturing" and key == "ENABLE_MANUFACTURING"
        )
        if not _entitled(company, key) and not granted_dark:
            out["unavailable"].append(key)
        elif key in snapshot and flags.get(key) != snapshot.get(key):
            out["kept_as_set"].append(key)
        elif flags.get(key) is True:
            out["already_on"].append(key)
        else:
            out["would_enable"].append(key)
    return out


@transaction.atomic
def apply_pack(company, pack: str, answers: dict, user):
    from accounts.models import Company, CompanyPackState

    if pack not in PACKS:
        from core.exceptions import BusinessRuleError

        raise BusinessRuleError("Unknown pack.")
    # Lock the company row so two concurrent confirm submissions (double
    # click, two tabs) read-modify-write feature_flags serially instead of
    # one silently discarding the other's changes.
    company = Company.objects.select_for_update().get(pk=company.pk)
    state, _ = CompanyPackState.objects.select_for_update().get_or_create(company=company)
    flags = dict(company.feature_flags or {})
    snapshot = dict(state.applied_flags or {})
    new_snapshot = dict(snapshot)
    skipped = []
    insurance_grant = pack == "insurance"
    manufacturing_grant = pack == "manufacturing"
    for key in PACKS[pack]:
        if key == "ENABLE_PAYROLL":
            continue
        # Dark modules stay off for retail, trade, and distribution. The
        # insurance pack grants ENABLE_CRM. The manufacturing pack grants
        # ENABLE_MANUFACTURING. Nothing else does.
        granted_dark = (insurance_grant and key == "ENABLE_CRM") or (
            manufacturing_grant and key == "ENABLE_MANUFACTURING"
        )
        if not _entitled(company, key) and not granted_dark:
            skipped.append(key)
            continue
        if key in snapshot and flags.get(key) != snapshot.get(key):
            continue
        flags[key] = True
        new_snapshot[key] = True
    if insurance_grant:
        flags["pack_grant"] = "insurance"
        new_snapshot["pack_grant"] = "insurance"
    if manufacturing_grant:
        flags["manufacturing_pack_grant"] = True
        new_snapshot["manufacturing_pack_grant"] = True
    company.feature_flags = flags
    company.save(update_fields=["feature_flags", "updated_at"])
    state.answers = {key: answers.get(key) for key in QUESTIONS}
    state.proposed_pack = pack
    state.applied_pack = pack
    state.applied_flags = new_snapshot
    state.confirmed_at = timezone.now()
    state.updated_by = user
    state.save()
    state.skipped_flags = skipped
    log_flag_event(company, "ENABLE_ARCHETYPE_PACKS", "pack_confirmed", pack=pack)
    from core.services.audit import AuditService

    AuditService.log(
        company=company, user=user, action="pack.apply", entity_type="CompanyPackState", entity_id=state.pk,
        description=f"Applied the {pack} pack",
        metadata={
            "pack": pack,
            "enabled": sorted(k for k in new_snapshot if k not in snapshot and new_snapshot[k] is True),
            "skipped": skipped,
        },
    )
    return state
