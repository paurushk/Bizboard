"""Runtime feature flags — company JSON merged with env toggles (Wave 17G)."""

from __future__ import annotations

from django.conf import settings


# "Dark" preview modules (see SPECTACULAR_SETTINGS description). The env flag is
# a hard deployment ceiling; a tenant only gets one via an explicit grant
# (company feature_flags JSON, or a subscription plan module). Once a company
# JSON names ANY module key, the other dark modules it did not name are off
# (opt-in once you touch them). Help-only keys (helpV2, item_custom_fields_v2)
# never trip that — a `{"helpV2": true}` pilot must not turn Manufacturing off.
DARK_MODULE_KEYS = (
    "ENABLE_MANUFACTURING",
    "ENABLE_PAYROLL",
    "ENABLE_CRM",
)

# Company JSON keys that are product flags, not module opt-ins.
NON_MODULE_OVERRIDE_KEYS = frozenset({"helpV2", "help_v2", "item_custom_fields_v2"})

# FLAG-01: rollout flags a per-company feature_flags entry may turn ON *above*
# the deployment default (staged rollout) as well as deny — the company value is
# authoritative both ways. Credential-backed integrations (Cashfree / PayU /
# WhatsApp Cloud / Account Aggregator) are deliberately NOT here: the deployment
# must actually be configured for them, so the env flag stays a hard ceiling and
# a company can only *narrow* it.
ROLLOUT_GRANTABLE_KEYS = frozenset({
    "ENABLE_POS",
    "ENABLE_GSTR",
    "ENABLE_TALLY",
    "ENABLE_GSTN_JSON",
    "ENABLE_SETUP_WIZARD",
    "ENABLE_TDS",
})

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
    # FLAG-03: one truthy convention across the codebase (1/true/yes/on,
    # case-insensitive) — mirrors settings._parse_debug_flag.
    val = getattr(settings, name, False)
    if val is True:
        return True
    if val is False or val is None:
        return False
    return str(val).strip().lower() in {"1", "true", "yes", "on"}


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
    # FLAG-02: the SPA asks for flags on boot and on every company switch, and
    # billing.plan_modules_for_company hits the DB each call. Memoise on the
    # Company instance, keyed on the inputs that can change the result, so a
    # test (or a within-request mutation) that edits feature_flags still recomputes.
    cache_ok = company is not None and user is None
    if cache_ok:
        key = (getattr(company, "pk", None), repr(getattr(company, "feature_flags", None)))
        cached = getattr(company, "_feature_flags_cache", None)
        if cached is not None and cached[0] == key:
            return dict(cached[1])
    result = _build_feature_flags_uncached(company=company, user=user)
    if cache_ok:
        try:
            company._feature_flags_cache = (key, dict(result))
        except Exception:  # noqa: BLE001 — company may be a lightweight stub
            pass
    return result


def _build_feature_flags_uncached(*, company=None, user=None) -> dict[str, bool]:
    env = {key: _env_bool(key) for key in ENV_FLAG_KEYS}
    flags: dict[str, bool] = dict(env)
    if company is not None:
        overrides = getattr(company, "feature_flags", None)
        overrides = overrides if isinstance(overrides, dict) else {}

        try:
            from billing.services import plan_modules_for_company

            plan_modules = plan_modules_for_company(company)
        except Exception:  # noqa: BLE001 — a billing outage must not silently grant paid modules
            plan_modules = None
        plan_modules = plan_modules if isinstance(plan_modules, dict) else {}

        # Has the company explicitly engaged with *module* flags? If so, a dark
        # module it did not name is off (opt-in once you touch them). helpV2 /
        # item_custom_fields_v2 do not count.
        module_keys_touched = [
            k
            for k in overrides
            if k not in NON_MODULE_OVERRIDE_KEYS
            and (k in ENV_FLAG_KEYS or k in DARK_MODULE_KEYS)
        ]

        for key in ENV_FLAG_KEYS:
            val = env[key]

            if key in DARK_MODULE_KEYS:
                # Preview modules — env is a hard ceiling.
                if key in plan_modules:
                    # The subscription plan is authoritative for a module it names.
                    val = env[key] and bool(plan_modules[key])
                elif plan_modules:
                    # A non-empty plan that omits this module = not entitled.
                    val = False
                else:
                    # No plan module info: grant it via the company JSON, else
                    # fall back to env-only (unless the company has engaged with
                    # module flags — then an un-named module is off).
                    granted = bool(overrides.get(key))
                    legacy_env_only = not module_keys_touched
                    val = env[key] and (granted or legacy_env_only)
                flags[key] = val
                continue

            # 1. subscription plan modules — a listed key narrows (a *grantable*
            #    key listed truthy also lifts). A key the plan does not mention
            #    is NOT a denial.
            if key in plan_modules:
                if key in ROLLOUT_GRANTABLE_KEYS:
                    val = bool(plan_modules[key])
                else:
                    val = val and bool(plan_modules[key])

            # 2. company feature_flags JSON.
            if key in overrides:
                if key in ROLLOUT_GRANTABLE_KEYS:
                    val = bool(overrides[key])          # staged rollout — both ways
                else:
                    val = val and bool(overrides[key])  # deny-only (env is the ceiling)

            flags[key] = val

        company_flags = overrides
        if "item_custom_fields_v2" in company_flags:
            flags["item_custom_fields_v2"] = bool(company_flags["item_custom_fields_v2"])
        else:
            # Intentional product default ON; JSON false is the kill-switch.
            # Documented in docs/requirements/ITEM_CUSTOM_FIELDS.md §8.6.
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
