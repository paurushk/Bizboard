"""Runtime feature flags — company JSON merged with env toggles (Wave 17G)."""

from __future__ import annotations

from django.conf import settings


# R1-024: "dark" preview modules (see SPECTACULAR_SETTINGS description). Once a
# company JSON lists any *module* key (ENV_FLAG_KEYS / DARK_MODULE_KEYS), these
# require an explicit per-company opt-in — the env flag is only a ceiling, never
# an auto-grant. Help-only keys (helpV2, item_custom_fields_v2) must not trip this,
# or a D5 pilot `{"helpV2": true}` would silently turn Manufacturing/Payroll/CRM off.
DARK_MODULE_KEYS = (
    "ENABLE_MANUFACTURING",
    "ENABLE_PAYROLL",
    "ENABLE_CRM",
)

# Company JSON keys that are product flags, not module opt-ins.
NON_MODULE_OVERRIDE_KEYS = frozenset({"helpV2", "help_v2", "item_custom_fields_v2"})

ENV_FLAG_KEYS = (
    "ENABLE_MANUFACTURING",
    "ENABLE_PAYROLL",
    "ENABLE_CRM",
    "ENABLE_TDS",
    "ENABLE_WHATSAPP_CLOUD",
    "ENABLE_ACCOUNT_AGGREGATOR",
    "ENABLE_CASHFREE",
    "ENABLE_PAYU",
    "ENABLE_POS",
    "ENABLE_SETUP_WIZARD",
    "ENABLE_GSTR",
    "ENABLE_TALLY",
    "ENABLE_GSTN_JSON",
)


def _env_bool(name: str) -> bool:
    return getattr(settings, name, False) is True or str(getattr(settings, name, "0")).strip() in (
        "1",
        "true",
        "True",
        "yes",
    )


def _help_v2_enabled(*, company, user, company_flags: dict) -> bool:
    """Per-company Help v2 flag (item_custom_fields_v2 pattern). Pre-GA default off.

    Internal: requesting user is_staff, or company id in HELP_V2_COMPANY_ALLOWLIST.
    Pilot: company JSON ``helpV2: true``.
    Kill-switch: JSON ``helpV2: false`` always wins when the key is present.
    GA default-on is a later one-line change of the fallback.
    """
    json_key = None
    if "helpV2" in company_flags:
        json_key = "helpV2"
    elif "help_v2" in company_flags:
        json_key = "help_v2"
    if json_key is not None:
        return bool(company_flags[json_key])
    if user is not None and bool(getattr(user, "is_staff", False)):
        return True
    allowlist = _help_v2_allowlist()
    company_id = getattr(company, "id", None) if company is not None else None
    if company_id is not None and int(company_id) in allowlist:
        return True
    return False


def _help_v2_allowlist() -> set[int]:
    raw = getattr(settings, "HELP_V2_COMPANY_ALLOWLIST", "") or ""
    out: set[int] = set()
    for part in str(raw).split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


def build_feature_flags(*, company=None, user=None) -> dict[str, bool]:
    flags: dict[str, bool] = {key: _env_bool(key) for key in ENV_FLAG_KEYS}
    if company is not None:
        overrides = getattr(company, "feature_flags", None) or {}
        if not isinstance(overrides, dict):
            overrides = {}
        for key, value in overrides.items():
            if key in ENV_FLAG_KEYS:
                flags[key] = flags[key] and bool(value)
        # R1-024: dark modules are opt-in once the company JSON lists a module
        # key. A company that never touched module flags (or only set helpV2)
        # keeps the legacy env-only behaviour.
        module_overrides = {
            key: value
            for key, value in overrides.items()
            if key not in NON_MODULE_OVERRIDE_KEYS
            and (key in ENV_FLAG_KEYS or key in DARK_MODULE_KEYS)
        }
        if module_overrides:
            for key in DARK_MODULE_KEYS:
                if key not in overrides:
                    flags[key] = False
        try:
            from billing.services import plan_modules_for_company

            plan_modules = plan_modules_for_company(company)
        except Exception:  # noqa: BLE001 — billing outage must fail closed for dark modules
            plan_modules = {key: False for key in DARK_MODULE_KEYS}
        if isinstance(plan_modules, dict):
            for key, value in plan_modules.items():
                if key in flags:
                    flags[key] = flags[key] and bool(value)
        company_flags = overrides if isinstance(overrides, dict) else {}
        if "item_custom_fields_v2" in company_flags:
            flags["item_custom_fields_v2"] = bool(company_flags["item_custom_fields_v2"])
        else:
            flags["item_custom_fields_v2"] = True
        flags["helpV2"] = _help_v2_enabled(company=company, user=user, company_flags=company_flags)
    else:
        flags["item_custom_fields_v2"] = True
        flags["helpV2"] = _help_v2_enabled(company=None, user=user, company_flags={})
    # Derived flags from existing company settings
    if company is not None:
        flags["ENABLE_ACCOUNTING"] = bool(getattr(company, "accounting_enabled", False))
        flags["ENABLE_AI"] = bool(getattr(company, "ai_features_enabled", False))
    else:
        flags["ENABLE_ACCOUNTING"] = False
        flags["ENABLE_AI"] = False
    return flags
