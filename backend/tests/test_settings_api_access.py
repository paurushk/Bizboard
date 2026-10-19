"""SET-01: what the API lets a plain staff user do on each Settings screen's endpoints.

The front end hides these screens behind `web/src/navigation/settingsAccess.ts`. This is the API
side of the same list: a screen the UI limits to the owner must refuse a plain staff user's
writes, and where the API is deliberately wider than the screen (reads other screens need), the
table says so, so the difference cannot grow unnoticed.

`tenant_a.staff_client` is a SALES_STAFF member with no capability flags.
"""

import pytest

V1 = "/api/v1/"

# (screen id in settingsAccess.ts, method, path, body)
OWNER_ONLY_WRITES = [
    ("company", "patch", "company/", {"name": "New Name"}),
    ("series", "patch", "sales/invoices/number-series/", {"prefix": "ZZ"}),
    ("series", "patch", "purchases/invoices/number-series/", {"prefix": "ZZ"}),
    ("units", "post", "masters/units/", {"name": "Dozen", "short_name": "dz"}),
    ("price-lists", "post", "masters/price-lists/", {"name": "Gold"}),
    ("payment-gateway", "patch", "payments/gateway-settings/", {"test_mode": True}),
    ("payment-gateway", "post", "payments/gateway-settings/verify/", {}),
    ("billing", "post", "billing/subscription/", {"action": "suspend", "churn_reason": "x"}),
    ("accounting-settings", "get", "accounting/settings/disable-preflight/", None),
    ("money-in-rules", "patch", "payments/money-in-rules/", {"cash_269st_mode": "off"}),
    ("accounting-settings", "post", "accounting/settings/", {"accounting_enabled": False}),
    ("users", "post", "company/users/", {"email": "x@y.test", "role": "VIEWER"}),
    ("gst", "post", "company/gstins/", {"gstin": "29AAAAA0000A1ZY"}),
    ("statutory-licences", "post", "company/statutory-licences/", {"licence_type": "FSSAI", "licence_number": "12345678901234"}),
    ("backup", "post", "company/export/", {}),
    ("pack-wizard", "post", "company/packs/", {"answers": {}}),
]

# Reads the API deliberately leaves open to staff because other screens need them.
OPEN_READS = [
    # The company profile is readable by every member (staff get a shorter set of fields).
    ("company", "get", "company/"),
]

OWNER_ONLY_READS = [
    # A staff member with no capability flags cannot read the series either; one who can create
    # sales can (CanViewSalesSurfaces), which the Series screen does not offer them.
    ("series", "get", "sales/invoices/number-series/"),
    ("users", "get", "company/users/"),
    ("statutory-licences", "get", "company/statutory-licences/"),
    ("gst", "get", "company/gstins/"),
    ("payment-gateway", "get", "payments/gateway-settings/"),
    ("money-in-rules", "get", "payments/money-in-rules/"),
    ("accounting-settings", "get", "accounting/settings/"),
]


def _call(client, method, path, body=None):
    fn = getattr(client, method)
    if method == "get":
        return fn(V1 + path)
    return fn(V1 + path, body or {}, format="json")


@pytest.mark.parametrize("screen,method,path,body", OWNER_ONLY_WRITES, ids=lambda v: v if isinstance(v, str) else "")
def test_staff_cannot_write_owner_only_settings(tenant_a, screen, method, path, body):
    r = _call(tenant_a.staff_client, method, path, body)
    assert r.status_code in (401, 403), f"{screen}: staff {method.upper()} {path} answered {r.status_code}"


@pytest.mark.parametrize("screen,method,path", OWNER_ONLY_READS, ids=lambda v: v if isinstance(v, str) else "")
def test_staff_cannot_read_owner_only_settings(tenant_a, screen, method, path):
    r = _call(tenant_a.staff_client, method, path)
    assert r.status_code in (401, 403), f"{screen}: staff GET {path} answered {r.status_code}"


@pytest.mark.parametrize("screen,method,path", OPEN_READS, ids=lambda v: v if isinstance(v, str) else "")
def test_documented_open_reads_stay_open_to_staff(tenant_a, screen, method, path):
    r = _call(tenant_a.staff_client, method, path)
    assert r.status_code == 200, f"{screen}: staff GET {path} answered {r.status_code}"


@pytest.mark.parametrize("screen,method,path", OWNER_ONLY_READS + OPEN_READS, ids=lambda v: v if isinstance(v, str) else "")
def test_owner_can_read_every_listed_settings_endpoint(tenant_a, screen, method, path):
    r = _call(tenant_a.client, method, path)
    assert r.status_code == 200, f"{screen}: owner GET {path} answered {r.status_code}"
