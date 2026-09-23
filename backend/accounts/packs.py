"""Named flag bundles. Entitlement and hand edits win over a pack."""

from __future__ import annotations

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
    ),
    "trade": (
        "ENABLE_CRM",
        "ENABLE_REPLENISHMENT",
        "ENABLE_PURCHASE_PLANNING",
        "ENABLE_SUPPLIER_PRICE_HISTORY",
        "ENABLE_ROUTE_PROFIT",
        "ENABLE_ORDER_GATES",
        "ENABLE_CUSTOMER_ACTIONS",
        "ENABLE_GST_GUARD",
        "ENABLE_ACTION_ASSIGNMENT",
        "ENABLE_CUSTOMER_360",
    ),
}

# Held until their features are the ones a distributor actually runs.
HELD_PACKS = ("distribution", "manufacturing")

QUESTIONS = ("what_you_sell", "how_you_sell", "deliver", "gst_registered")


def propose_pack(answers: dict) -> str:
    how = (answers.get("how_you_sell") or "").strip().lower()
    if how == "counter":
        return "retail"
    return "trade"


def _entitled(company, key: str) -> bool:
    """Match the flag service. A dark module a plan does not name stays off."""
    from core.services.feature_flags import DARK_MODULE_KEYS

    modules = plan_modules_for_company(company)
    if not isinstance(modules, dict):
        return True
    if key in modules:
        return bool(modules[key])
    if key in DARK_MODULE_KEYS:
        return False
    return True


def apply_pack(company, pack: str, answers: dict, user):
    from accounts.models import CompanyPackState

    if pack not in PACKS:
        from core.exceptions import BusinessRuleError

        raise BusinessRuleError("Unknown pack.")
    state, _ = CompanyPackState.objects.get_or_create(company=company)
    flags = dict(company.feature_flags or {})
    snapshot = dict(state.applied_flags or {})
    new_snapshot = dict(snapshot)
    skipped = []
    for key in PACKS[pack]:
        if key == "ENABLE_PAYROLL":
            continue
        if not _entitled(company, key):
            skipped.append(key)
            continue
        if key in snapshot and flags.get(key) != snapshot.get(key):
            continue
        flags[key] = True
        new_snapshot[key] = True
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
    return state
