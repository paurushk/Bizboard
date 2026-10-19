"""SET-14: every settings error code is really raised somewhere, and none is raised without being listed."""

import re
from pathlib import Path

from core.settings_codes import SETTINGS_ERROR_CODES

BACKEND = Path(__file__).resolve().parents[1]
SETTINGS_FILES = [
    "accounts/views.py",
    "accounts/series_views.py",
    "accounts/export_views.py",
    "accounting/views.py",
    "billing/reauth.py",
    "billing/views.py",
    "core/settings_writes.py",
    "masters/views.py",
    "payments/services.py",
    "payments/views.py",
]


def _source() -> str:
    return "\n".join((BACKEND / f).read_text(encoding="utf-8") for f in SETTINGS_FILES)


def test_every_listed_code_is_raised_in_the_settings_code():
    source = _source()
    for code in SETTINGS_ERROR_CODES:
        assert re.search(rf'code="{re.escape(code)}"', source), f"{code} is listed but never raised"


def test_codes_are_unique():
    assert len(set(SETTINGS_ERROR_CODES)) == len(SETTINGS_ERROR_CODES)


def test_a_licence_delete_when_locked_carries_its_code(tenant_a):
    from accounts.models import CompanyStatutoryLicence
    from django.utils import timezone

    lic = CompanyStatutoryLicence.objects.create(
        company=tenant_a.company, licence_type="FSSAI", licence_number="X1", locked_at=timezone.now()
    )
    r = tenant_a.client.delete(f"/api/v1/company/statutory-licences/{lic.pk}/")
    assert r.status_code == 400
    assert "LICENCE_LOCKED" in str(r.data)
