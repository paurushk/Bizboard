"""Runtime feature flags — company JSON merged with env toggles (Wave 17G)."""

from __future__ import annotations

from django.conf import settings


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


def build_feature_flags(*, company=None) -> dict[str, bool]:
    flags: dict[str, bool] = {key: _env_bool(key) for key in ENV_FLAG_KEYS}
    if company is not None:
        overrides = getattr(company, "feature_flags", None) or {}
        if isinstance(overrides, dict):
            for key, value in overrides.items():
                if key in ENV_FLAG_KEYS:
                    flags[key] = bool(value)
        try:
            from billing.services import plan_modules_for_company

            plan_modules = plan_modules_for_company(company)
        except Exception:  # noqa: BLE001 — flags must not fail if billing is unavailable
            plan_modules = None
        if isinstance(plan_modules, dict):
            for key, value in plan_modules.items():
                if key in flags:
                    flags[key] = flags[key] and bool(value)
    # Derived flags from existing company settings
    if company is not None:
        flags["ENABLE_ACCOUNTING"] = bool(getattr(company, "accounting_enabled", False))
        flags["ENABLE_AI"] = bool(getattr(company, "ai_features_enabled", False))
    else:
        flags["ENABLE_ACCOUNTING"] = False
        flags["ENABLE_AI"] = False
    return flags
