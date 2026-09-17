"""14.7 — freeze-list flag lifecycle: seeded paid plans never grant Table B."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings

from billing.entitlements import FREEZE_DARK_PLAN_MODULES
from core.services.feature_flags import DARK_MODULE_KEYS, ENV_FLAG_KEYS, ROLLOUT_GRANTABLE_KEYS

ROOT = Path(__file__).resolve().parents[2]


def test_freeze_dark_modules_are_known_env_flags():
    for key in FREEZE_DARK_PLAN_MODULES:
        assert key in ENV_FLAG_KEYS, key
    for key in ("ENABLE_MANUFACTURING", "ENABLE_PAYROLL", "ENABLE_CRM"):
        assert key in DARK_MODULE_KEYS
        assert key in FREEZE_DARK_PLAN_MODULES
    assert "ENABLE_GSTR" in FREEZE_DARK_PLAN_MODULES
    assert "ENABLE_TALLY" in FREEZE_DARK_PLAN_MODULES
    assert "ENABLE_POS" not in FREEZE_DARK_PLAN_MODULES
    assert "ENABLE_POS" in ROLLOUT_GRANTABLE_KEYS
    # D6/D10 are env ceilings, not paid-plan grants.
    assert "ENABLE_FIXED_ASSETS" not in FREEZE_DARK_PLAN_MODULES
    assert "ENABLE_BOE" not in FREEZE_DARK_PLAN_MODULES
    assert "ENABLE_FIXED_ASSETS" not in ROLLOUT_GRANTABLE_KEYS
    assert "ENABLE_BOE" not in ROLLOUT_GRANTABLE_KEYS


def test_env_flag_keys_exist_on_settings():
    for key in ENV_FLAG_KEYS:
        assert hasattr(settings, key), key


def test_known_limitation_flags_default_off_in_settings_source():
    src = (ROOT / "backend" / "config" / "settings.py").read_text(encoding="utf-8")
    assert '_env_bool("ENABLE_FIXED_ASSETS", "0")' in src
    assert '_env_bool("ENABLE_BOE", "0")' in src
    fa = (ROOT / "backend" / "accounting" / "views.py").read_text(encoding="utf-8")
    boe = (ROOT / "backend" / "purchases" / "views.py").read_text(encoding="utf-8")
    assert 'getattr(settings, "ENABLE_FIXED_ASSETS", False)' in fa
    assert 'getattr(settings, "ENABLE_BOE", False)' in boe
    # Test settings still opt in so WF-53 / WF-57 keep exercising the surface.
    test_src = (ROOT / "backend" / "config" / "settings_test.py").read_text(encoding="utf-8")
    assert "ENABLE_FIXED_ASSETS = True" in test_src
    assert "ENABLE_BOE = True" in test_src
